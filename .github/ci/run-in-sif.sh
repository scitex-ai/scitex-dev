#!/usr/bin/env bash
# Runs INSIDE the reused scitex-ci SIF (apptainer exec). $1 = python version.
#
# WHY a layered install (not the bare PYTHONPATH=src trick scitex-dev uses):
# the shared ci-cpu.sif bakes scitex-dev[all,dev] DEPS, NOT scitex-dev's —
# matplotlib / graphviz / seaborn / django / Pillow / networkx / playwright /
# pytesseract / scitex-app / scitex-ui are absent from the SIF. So we install
# THIS checkout + its [all,dev] extras (WITH dependency resolution) into a
# writable --target dir and prepend that on PYTHONPATH. The SIF still supplies
# the heavy shared base (pip/uv, the python interpreters, scitex-dev's deps),
# so only scitex-dev's own thin dep set is fetched per run.
#
# --target (not a plain `-e .`): the SIF's /opt/venv-* are root-owned + RO and
# the HPC compute-node HOME is RO inside the container, so a normal site install
# fails Permission denied. A writable target on node-local /tmp sidesteps both.
#
# Fail-loud: a missing interpreter or a failed install is a hard error.
set -euo pipefail

V="${1:?python version arg required (3.11/3.12/3.13)}"
VENV="/opt/venv-$V"
test -x "$VENV/bin/python" || {
    echo "::error::baked python missing in $VENV — rebuild the SIF: scitex-container apptainer build ci-cpu"
    exit 1
}

mapfile -t PG_INITDB_CANDIDATES < <(compgen -G '/usr/lib/postgresql/*/bin/initdb' | sort -V)
[ "${#PG_INITDB_CANDIDATES[@]}" -gt 0 ] || {
    echo "::error::CI image lacks PostgreSQL server binaries under /usr/lib/postgresql/*/bin. Rebuild and synchronize ci-cpu.sif; host binaries are not an allowed fallback."
    exit 1
}
PGBIN="$(dirname "${PG_INITDB_CANDIDATES[-1]}")"
for required in initdb pg_ctl postgres; do
    [ -x "$PGBIN/$required" ] || {
        echo "::error::CI image PostgreSQL capability is incomplete: $PGBIN/$required is not executable. Rebuild and synchronize ci-cpu.sif."
        exit 1
    }
done
PSQL="$(command -v psql 2>/dev/null || true)"
[ -x "$PSQL" ] || {
    echo "::error::CI image PostgreSQL capability is incomplete: psql is not executable. Rebuild and synchronize ci-cpu.sif."
    exit 1
}

export LC_ALL=C.UTF-8 LANG=C.UTF-8

# Real writable scratch. The runner profile exports TMPDIR=~/.cache/tmp, a host
# path that does NOT resolve inside the container; tests (tmp_path) and the
# install target both need a working, writable tmp. Per-version-isolated so
# concurrent matrix legs don't collide.
#
# SCRATCH-FIRST, NOT /tmp. This used to hardcode /tmp, and on the SciTeX compute
# nodes /tmp lives on the SMALL root LV (compute-02: 98G, reached 99% full, 1.3G
# free) while /scratch is a separate multi-terabyte LV with hundreds of GB free.
# The cost was measured, not hypothetical: a release leg died with Errno 28
# unpacking wheels into /tmp/ci-figrecipe-*, and an audit leg failed twice the
# same way. This directory is the consumer - the wrapper's own temp, holding the
# uv cache and the unpacked wheels - so pointing it at scratch fixes the pressure
# at its source rather than by relocating the host's /tmp, which would be far
# more dangerous (the live tmux server socket lives there, and sac's liveness
# probe is tmux-based, so hiding it reads every agent on the host as dead).
#
# Falls back to /tmp when there is no scratch volume, so this stays correct on
# hosts that only have the one filesystem.
_CI_TMP_ROOT="/scratch/ywatanabe/ci/tmp"
# THE FALLBACK MUST BE LOUD, AND MUST DISTINGUISH TWO DIFFERENT THINGS.
#
# This was `[ -d /scratch ] || _CI_TMP_ROOT="/tmp"` - a silent fallback. It made
# the whole change capable of becoming a NO-OP THAT LOOKS SUCCESSFUL: if the
# scratch test failed for any reason at all, the wrapper quietly put the temp
# back on the root LV, which is exactly where this change exists to keep it off.
# The red legs on this branch showed the fallback winning - a failure path of
# /tmp/ci-scitex_dev-<run>-..., the pre-change location - with nothing in the log
# saying the scratch-first intent had been abandoned.
#
# There are two different situations and they deserve different answers:
#   - this HOST has no scratch volume (one filesystem): /tmp is correct, and
#     falling back is right. Say so.
#   - scratch EXISTS but this run cannot see or write it (a container boundary,
#     a mount or permission change): that is a MISCONFIGURATION, and silently
#     using /tmp would recreate the pressure this change removes. FAIL, so it is
#     noticed the first time rather than after the next ENOSPC.
if [ -d /scratch ]; then
  if ! mkdir -p "$_CI_TMP_ROOT" 2>/dev/null || [ ! -w "$_CI_TMP_ROOT" ]; then
    printf 'ERROR: /scratch exists but %s is not writable from this run.\n' "$_CI_TMP_ROOT" >&2
    printf '       Refusing to fall back to /tmp: that is the root LV this change\n' >&2
    printf '       exists to keep the CI temp off, and a silent fallback here is\n' >&2
    printf '       how the change becomes a no-op that reports success.\n' >&2
    exit 1
  fi
else
  _CI_TMP_ROOT="/tmp"
  printf 'NOTICE: no /scratch on this host; CI temp stays on /tmp (single-filesystem host).\n' >&2
fi

# Age-based sweep of superseded per-run trees. These are disposable by
# construction (one per run x attempt x version), nothing cleans them today, and
# on the scratch volume an unbounded accumulation would simply take longer to
# hurt. +1 day so a run in flight can never be swept by a concurrent leg.
find "$_CI_TMP_ROOT" -maxdepth 1 -name 'ci-*' -type d -mtime +1 -exec rm -rf {} + 2>/dev/null || true

export TMPDIR="$_CI_TMP_ROOT/ci-scitex_dev-${GITHUB_RUN_ID:-0}-${GITHUB_RUN_ATTEMPT:-0}-$V"
# `${TMPDIR:?}` AND NOT `$TMPDIR`.
#
# The line above cannot produce an empty value TODAY — `$_CI_TMP_ROOT` is
# assigned from a LITERAL in both branches of the `[ -d /scratch ]` test above,
# so it is always non-empty, and the rest is literal. The guard pins that.
#
# THAT INVARIANT IS NOW LESS VISIBLE THAN IT WAS, and it is worth saying so:
# this line used to start with the literal `/tmp/`, so "always non-empty" could
# be read off the deletion site. The prefix is a variable now. That is EXACTLY
# the shape this comment was written to warn about — scitex-agent-container's
# wrappers moved the name into a helper in another file and nothing there would
# have noticed an empty value. So: if `_CI_TMP_ROOT` ever grows a code path that
# can leave it unset, this guard becomes the only thing standing between an
# empty TMPDIR and an `rm -rf ""` that exits 0 silently.
#
# And `rm -rf ""` IS NOT A SAFE NO-OP. Measured, GNU coreutils 9.4: `-f` treats
# the empty operand as a nonexistent file, so it exits 0 SILENTLY — `set -euo
# pipefail` catches nothing, and the script CONTINUES with TMPDIR="". Every
# later use is then a path off the filesystem root: `"$TMPDIR/site"` is `/site`.
# The empty value is dangerous precisely because it is quiet.
rm -rf "${TMPDIR:?ci scratch path is empty — refusing to rm -rf it}"
mkdir -p "$TMPDIR/site" "$TMPDIR/uv-cache"

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
# every CI run; the xdist workers (one per core, see below) then each cold-start
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

echo "py=$("$VENV/bin/python" -V) target=$TMPDIR/site"

# The full declared test environment is mandatory. A reduced-extra fallback can
# make the same commit pass or fail depending on resolver timing, so it is not
# a valid CI environment.
uv pip install --python "$VENV/bin/python" --target="$TMPDIR/site" -e ".[all,dev]"

export PYTHONPATH="$TMPDIR/site:$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

PGDIR="$TMPDIR/postgres"
mkdir -p "$PGDIR"
cleanup_postgres() {
    "$PGBIN/pg_ctl" -D "$PGDIR/data" -m immediate stop >/dev/null 2>&1 || true
}
trap cleanup_postgres EXIT
"$PGBIN/initdb" -D "$PGDIR/data" -A trust --encoding=UTF8 -U postgres >"$PGDIR/initdb.log" 2>&1 || {
    echo "::error::PostgreSQL initdb failed in the verified CI image"
    tail -40 "$PGDIR/initdb.log"
    exit 1
}
"$PGBIN/pg_ctl" -D "$PGDIR/data" -o "-k $PGDIR -h ''" -w -t 60 start >"$PGDIR/start.log" 2>&1 || {
    echo "::error::throwaway PostgreSQL cluster failed to start"
    tail -40 "$PGDIR/start.log"
    exit 1
}
PGHOST_ENC="$(printf '%s' "$PGDIR" | sed 's|/|%2F|g')"
export SCITEX_STORE_DSN="postgresql://postgres@${PGHOST_ENC}/postgres"
"$PSQL" -h "$PGDIR" -U postgres -d postgres -Atqc 'select 1' | grep -qx 1 || {
    echo "::error::throwaway PostgreSQL cluster failed its readiness query"
    exit 1
}
echo "postgres=$($PGBIN/postgres --version) socket=$PGDIR readiness=verified"

# Parallelise with pytest-xdist (baked in [dev]/[all,dev] as pytest-xdist>=3).
# scitex-dev's suite is ~2460 tests; single-process it overran the job's old
# 30-min cap (2300 passed in ~28 min, cancelled at 96%). Each xdist worker is
# a SEPARATE PROCESS, so matplotlib's global rcParams / pyplot state and the
# scitex-dev style-stack are naturally isolated per worker — the safe way to
# parallelise a matplotlib-heavy suite.
#
# Worker count: use ALL cores. Each matrix leg now runs on its own dedicated
# self-hosted node (one runner per node: scitex-dev-01/02/03), so there is no
# co-tenant to yield half the box to — the old nproc//2 cap left 2x the cores
# idle. nice/ionice (below) handles the "yield to higher-priority work if the
# node is ever shared" concern instead of statically reserving half the CPUs.
# Floor 4. pyproject addopts carries `-v`; override to `-q` here — 2460 verbose
# lines x workers bloats the CI log and adds measurable overhead.
NPROC="$(nproc 2>/dev/null || echo 4)"
WORKERS=$NPROC
[ "$WORKERS" -lt 4 ] && WORKERS=4
echo "xdist workers=$WORKERS (nproc=$NPROC)"

# Warm the matplotlib font cache ONCE, single-process, before xdist forks the
# workers. This builds $MPLCONFIGDIR/fontlist-*.json a single time so every
# worker reads a complete, consistent cache instead of racing to build it
# concurrently (the source of the render1!=render2 reproducibility flakes).
# Fail-loud: if matplotlib can't even build its font cache, CI must surface it.
# matplotlib may not be a dependency of this package; only warm the
# font cache when it's importable (no-op otherwise — never fail the run
# on an optional warm-up).
if python -c "import matplotlib" 2>/dev/null; then
  python -c "import matplotlib; matplotlib.use('Agg'); from matplotlib import font_manager; font_manager.fontManager; import matplotlib.pyplot as plt; f=plt.figure(); f.canvas.draw(); print('mpl font cache warmed at', matplotlib.get_cachedir())"
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
# cores but YIELDS the CPU and disk to any higher-priority process — "all
# available CPUs, with priority handling". The shell remains alive so its EXIT
# trap always stops the private PostgreSQL cluster.
nice -n 19 ionice -c 3 \
    python -m pytest tests/ -n "$WORKERS" --dist load -q \
    --cov=src/scitex_dev --cov-report=xml --cov-report=term \
    -p no:cacheprovider
