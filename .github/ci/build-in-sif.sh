#!/usr/bin/env bash
# Runs INSIDE the approved, versioned CI SIF through exec-in-sif.sh.
# Install the build frontend into job-owned writable scratch, then run the
# normal isolated PEP517 build of this checkout's wheel and sdist.
# Missing interpreters, failed builds or broken wheel entry points fail loud.
set -euo pipefail

V="${1:-3.12}"
VENV="/opt/venv-$V"
PY="$VENV/bin/python"
test -x "$PY" || {
    echo "::error::baked python missing in $VENV — rebuild the SIF: scitex-container apptainer build ci-cpu"
    exit 1
}

export LC_ALL=C.UTF-8 LANG=C.UTF-8

# Writable scratch (the runner's TMPDIR=~/.cache/tmp is a host path that does
# NOT resolve inside the container). Node-local /tmp is writable + ephemeral.
TMPDIR="/tmp/build-scitex_dev-${GITHUB_RUN_ID:-0}-${GITHUB_RUN_ATTEMPT:-0}-$V"
export TMPDIR
# `${TMPDIR:?}` — see run-in-sif.sh for the reasoning and the measurement.
# Short version: `rm -rf ""` exits 0 SILENTLY on GNU coreutils, so an empty name
# would delete nothing, fail nothing, and leave the rest of the script
# addressing paths off the filesystem root. `:?` aborts instead.
rm -rf "${TMPDIR:?build scratch path is empty — refusing to rm -rf it}"
mkdir -p "$TMPDIR/site" "$TMPDIR/uv-cache"

# The compute-node $HOME is RO inside the container — point every cache the
# installer might touch at the writable scratch (else uv/pip die creating
# ~/.cache).
source "$(dirname "${BASH_SOURCE[0]}")/release-context.sh"
scitex_release_context "$TMPDIR" "$VENV"
echo "build: py=$(scitex_release_run "$PY" -V) target=$TMPDIR/site"

# Install the PEP 517 build frontend into the writable target (uv fast path,
# pip safety net), then build with it. Clean dist/ first so only the freshly
# built artifacts are uploaded.
scitex_release_run uv pip install --python "$PY" --target="$TMPDIR/site" build ||
    scitex_release_run "$PY" -m pip install --target="$TMPDIR/site" build

rm -rf dist
scitex_release_run env PYTHONPATH="$TMPDIR/site" "$PY" -m build --outdir dist

echo "=== built artifacts ==="
ls -l dist
# fail-loud: refuse to continue the pipeline with an empty dist/.
test -n "$(ls -A dist 2>/dev/null)" || {
    echo "::error::python -m build produced no artifacts in dist/"
    exit 1
}

# --- Release gate: every declared entry point must IMPORT from the WHEEL ---
#
# A dangling entry point does not fail the build on its own: the wheel
# uploads, `pip install` succeeds, and the breakage lands in the USER's
# tooling. `pytest11` is imported by pytest at startup, so a dangling target
# aborts EVERY pytest run in the installed environment before collection.
# This step moves that failure back into the build.
#
# The audit runs against the freshly built WHEEL (unpacked to a temp dir),
# not against pyproject.toml — a correct declaration can still point at a
# module the build dropped, which is exactly the bug a source-only check
# would miss. The SIF has scitex-dev's runtime deps installed, so a genuine
# import failure means the ARTIFACT is broken, not the environment.
echo "=== entry-point import gate (built wheel) ==="
WHEEL="$(ls dist/*.whl | head -n 1)"
test -n "$WHEEL" || {
    echo "::error::no wheel in dist/ to audit"
    exit 1
}
scitex_release_run env PYTHONPATH="$PWD/src:$TMPDIR/site" "$PY" - "$WHEEL" <<'PYGATE'
import sys

from scitex_dev._release.entrypoint_imports import (
    audit_wheel_entry_point_imports,
)

report = audit_wheel_entry_point_imports(sys.argv[1], "scitex-dev")
sys.stdout.write(report.report() + "\n")
if not report.is_clean:
    sys.stdout.write(
        "::error::the built wheel declares entry points that do NOT import; "
        "publishing it would break `pytest` (and console scripts) for every "
        "user who installs it\n"
    )
    raise SystemExit(1)
PYGATE
