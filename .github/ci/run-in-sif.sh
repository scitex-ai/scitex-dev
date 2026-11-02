#!/usr/bin/env bash
# Runs INSIDE the approved, versioned CI SIF. $1 = Python3.11/3.12/3.13.
# Resolve THIS checkout's complete [all,dev] requirements into job-owned
# writable scratch. The target precedes the image's baked packages, so the
# selected source and declared dependencies determine the test environment.
# A --target install permits use of the image's read-only interpreter.
# Missing interpreters or failed resolution are hard errors.
set -euo pipefail

V="${1:?python version arg required (3.11/3.12/3.13)}"
VENV="/opt/venv-$V"
test -x "$VENV/bin/python" || {
    echo "::error::baked python missing in $VENV — rebuild the SIF: scitex-container apptainer build ci-cpu"
    exit 1
}

# The central registered image profile declares these exact capabilities.
# No highest-version search, home binary or host fallback is accepted.
PGBIN="${SCITEX_CI_PG_BIN:?registered image PostgreSQL directory is required}"
PG_CAPABILITY_VERSION="${SCITEX_CI_PG_VERSION:?registered image PostgreSQL version is required}"
PSQL="$PGBIN/psql"

export LC_ALL=C.UTF-8 LANG=C.UTF-8

# The audit protocol uses canonical level prefixes. A supported debug logger
# format adds bracketed source locations; those are deliberately not exempted
# by the strict finding classifier. State the CI format before any imports.
export SCITEX_LOGGING_FORMAT=default SCITEX_LOG_FORMAT=default

# Real writable scratch. The runner profile exports TMPDIR=~/.cache/tmp, a host
# path that does NOT resolve inside the container; tests (tmp_path) and the
# install target both need a working, writable tmp. Node-local /tmp is writable
# + ephemeral and per-version-isolated so concurrent matrix legs don't collide.
export TMPDIR="/tmp/ci-scitex_dev-${GITHUB_RUN_ID:-0}-${GITHUB_RUN_ATTEMPT:-0}-$V"
# `${TMPDIR:?}` AND NOT `$TMPDIR`.
#
# The line above cannot produce an empty value TODAY — the `/tmp/…` prefix is a
# literal. The guard pins that. scitex-agent-container's wrappers started from
# this exact shape and later moved the name into a helper function in another
# file, at which point "always non-empty" stopped being visible from the
# deletion site; nothing there would have noticed.
#
# And `rm -rf ""` IS NOT A SAFE NO-OP. Measured, GNU coreutils 9.4: `-f` treats
# the empty operand as a nonexistent file, so it exits 0 SILENTLY — `set -euo
# pipefail` catches nothing, and the script CONTINUES with TMPDIR="". Every
# later use is then a path off the filesystem root: `"$TMPDIR/site"` is `/site`.
# The empty value is dangerous precisely because it is quiet.
rm -rf "${TMPDIR:?ci scratch path is empty — refusing to rm -rf it}"
mkdir -p "$TMPDIR/site" "$TMPDIR/uv-cache"

# Set owned state before the installer or any application/plugin import.
source "$(dirname "${BASH_SOURCE[0]}")/release-context.sh"
scitex_release_context "$TMPDIR" "$VENV"

# Verify the declared image server/client closure in the neutral environment,
# before dependency resolution or a test/plugin can run.
scitex_release_run "$VENV/bin/python" -I -S -B \
    "$(dirname "${BASH_SOURCE[0]}")/verify-postgres-capability.py" \
    --bin-dir "$PGBIN" --expected-version "$PG_CAPABILITY_VERSION"

# The HPC compute-node $HOME is READ-ONLY inside the container, so uv/pip cannot
# create their default caches under ~/.cache — point them at the writable
# scratch instead (else `uv pip install` dies: "failed to create directory
# ~/.cache/uv: File exists / read-only").
export UV_CACHE_DIR="$TMPDIR/uv-cache"
export XDG_CACHE_HOME="$TMPDIR"
export PIP_CACHE_DIR="$TMPDIR/pip-cache"

# Headless matplotlib — no DISPLAY on the compute node; force the Agg backend so
# pyplot imports + figure rendering in the test suite never try to open a GUI.
export MPLBACKEND=Agg

# Dedicated, stable matplotlib config/cache dir for this matrix leg. Without
# pinning it, MPLCONFIGDIR defaults to $XDG_CACHE_HOME/matplotlib which is COLD
# every CI run; the bounded xdist workers (see below) then each cold-start
# matplotlib and RACE to build fontList.json in that shared dir.
# A partial/contended cache makes some renders fall back to a different font, so
# scitex-dev's reproducibility tests (validate_recipe renders the SAME recipe
# twice and compares) see render1 != render2 → spurious MSE-over-threshold
# failures (e.g. TestValidateRecipe, max channel diff 255). One stable dir +
# a single warm-up below (build the cache ONCE, pre-fork) removes the race.
export MPLCONFIGDIR="$TMPDIR/mpl"
mkdir -p "$MPLCONFIGDIR"

# A VIRTUAL_ENV leaked from the runner profile (~/.env-3.11) is a broken symlink
# in here; unset it so no tool (uv, pip) tries to follow it.
unset VIRTUAL_ENV || true

# venv bin on PATH (this matrix leg's python3 + pip); PYTHONPATH points at the
# writable target so imports + coverage use the freshly-installed checkout.
export PATH="$VENV/bin:$PATH"

echo "py=$(scitex_release_run "$VENV/bin/python" -V) target=$TMPDIR/site"

# The full declared test environment is mandatory. A reduced-extra fallback can
# make the same commit pass or fail depending on resolver timing, so it is not
# a valid CI environment.
scitex_release_run uv pip install --python "$VENV/bin/python" --target="$TMPDIR/site" -e ".[all,dev]"

PGDIR="$TMPDIR/postgres"
mkdir -p "$PGDIR"
cleanup_postgres() {
    scitex_release_run "$PGBIN/pg_ctl" -D "$PGDIR/data" -m immediate stop >/dev/null 2>&1 || true
}
trap cleanup_postgres EXIT
scitex_release_run "$PGBIN/initdb" -D "$PGDIR/data" -A trust --encoding=UTF8 -U postgres >"$PGDIR/initdb.log" 2>&1 || {
    echo "::error::PostgreSQL initdb failed in the verified CI image"
    tail -40 "$PGDIR/initdb.log"
    exit 1
}
scitex_release_run "$PGBIN/pg_ctl" -D "$PGDIR/data" -o "-k $PGDIR -h '' -p 5432" -w -t 60 start >"$PGDIR/start.log" 2>&1 || {
    echo "::error::throwaway PostgreSQL cluster failed to start"
    tail -40 "$PGDIR/start.log"
    exit 1
}
PGHOST_ENC="$(printf '%s' "$PGDIR" | sed 's|/|%2F|g')"
export SCITEX_STORE_DSN="postgresql://postgres@${PGHOST_ENC}/postgres"
scitex_release_run env "PGPASSFILE=$TMPDIR/refused-pgpass" "$PSQL" -X -h "$PGDIR" -p 5432 -U postgres -d postgres -Atqc 'select 1' | grep -qx 1 || {
    echo "::error::throwaway PostgreSQL cluster failed its readiness query"
    exit 1
}
echo "postgres=$($PGBIN/postgres --version) socket=$PGDIR readiness=verified"

# Only this verified socket-only cluster replaces the refused import-time
# endpoint. Keep every other application setting in the literal allowlist.
scitex_test_run() {
    scitex_release_run env \
        "PYTHONPATH=$TMPDIR/site:$PWD/src" \
        "MPLBACKEND=Agg" "MPLCONFIGDIR=$MPLCONFIGDIR" \
        "PGHOST=$PGDIR" "PGPORT=5432" "PGUSER=postgres" "PGDATABASE=postgres" \
        "PGPASSFILE=$TMPDIR/refused-pgpass" "SCITEX_STORE_DSN=$SCITEX_STORE_DSN" "$@"
}

# Parallelise with pytest-xdist within this shared runner job's budget.
# Company hosts run several independent runner services; nproc describes their
# shared allocation, not an exclusive allocation for this matrix leg. Keep a
# reviewed maximum of four workers and respect narrower affinity/CPU quotas.
WORKERS=$("$VENV/bin/python" -I -S - <<'PYWORKERS'
import os
from pathlib import Path

raw = os.environ.get("CI_XDIST_WORKERS") or "4"
if not raw.isascii() or not raw.isdecimal() or not 1 <= int(raw) <= 4:
    raise SystemExit("CI_XDIST_WORKERS must be an integer between 1 and 4")
limits = [int(raw), os.cpu_count() or 1]
if hasattr(os, "sched_getaffinity"):
    limits.append(len(os.sched_getaffinity(0)))
try:
    quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    if quota != "max":
        limits.append(max(1, int(quota) // int(period)))
except FileNotFoundError:
    try:
        root = Path("/sys/fs/cgroup/cpu")
        quota = int((root / "cpu.cfs_quota_us").read_text())
        period = int((root / "cpu.cfs_period_us").read_text())
        if quota > 0:
            limits.append(max(1, quota // period))
    except FileNotFoundError:
        pass
print(max(1, min(limits)))
PYWORKERS
)
echo "xdist workers=$WORKERS (shared-job maximum=4)"

# Warm the matplotlib font cache ONCE, single-process, before xdist forks the
# workers. This builds $MPLCONFIGDIR/fontlist-*.json a single time so every
# worker reads a complete, consistent cache instead of racing to build it
# concurrently (the source of the render1!=render2 reproducibility flakes).
# Fail-loud: if matplotlib can't even build its font cache, CI must surface it.
# matplotlib may not be a dependency of this package; only warm the
# font cache when it's importable (no-op otherwise — never fail the run
# on an optional warm-up).
if scitex_test_run python -c "import matplotlib" 2>/dev/null; then
  scitex_test_run python -c "import matplotlib; matplotlib.use('Agg'); from matplotlib import font_manager; font_manager.fontManager; import matplotlib.pyplot as plt; f=plt.figure(); f.canvas.draw(); print('mpl font cache warmed at', matplotlib.get_cachedir())"
else
  echo "matplotlib not importable — skipping font-cache warm-up (not a dep)"
fi

# Distribution: `--dist load` (per-TEST round-robin), NOT `--dist loadscope`.
# loadscope pins an entire MODULE's tests to ONE worker — and scitex-dev's heavy
# suites are big SINGLE modules (e.g. tests/integration/test_all_plotters_*.py
# parametrize one test over all 47 plotters, ~28 s each). loadscope therefore
# ran all ~50+ cases of such a module SERIALLY on one worker (~25 min) while the
# rest idled. There are NO module/session/class-scoped fixtures in those heavy
# modules and the root conftest's autouse `_close_figures` resets pyplot state
# after EVERY test, so loadscope's "same worker per module" buys nothing here —
# it only serialized. `load` spreads the parametrized cases across ALL workers.
#
# nice -n 19 ionice -c 3: run at the lowest CPU + idle I/O priority so that if
# this node is ever shared with interactive/dev work, CI grabs otherwise-idle
# CPU within its worker budget and yields to higher-priority processes.
# The shell remains alive so its EXIT trap always stops the private PostgreSQL
# cluster.
scitex_test_run nice -n 19 ionice -c 3 \
    python -m pytest tests/ -n "$WORKERS" --dist load -q \
    --cov=src/scitex_dev --cov-report=xml --cov-report=term \
    -p no:cacheprovider
