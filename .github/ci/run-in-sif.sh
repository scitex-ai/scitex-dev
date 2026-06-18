#!/usr/bin/env bash
# Runs INSIDE the reused CI SIF (apptainer exec). $1 = python version.
#
# The SIF has scitex-dev[all,dev] FULLY installed and is READ-ONLY. CI must run
# the CHECKOUT's code, so we prepend it on PYTHONPATH — that shadows the baked
# package for imports + coverage, while the baked install still supplies the
# importlib.metadata-backed surface a bare PYTHONPATH cannot:
#   - the `scitex-dev` console script on PATH   (skills subprocess tests)
#   - the `console_scripts` ENTRY POINT          (audit-cli resolves the CLI via
#                                                 importlib.metadata; ep.load()
#                                                 then imports the checkout's
#                                                 scitex_dev._cli via PYTHONPATH)
#   - a real __version__
# No install, no --writable-tmpfs: nothing is written into the SIF (the baked
# venv is root-owned — a runtime install hits Permission denied even on a
# tmpfs overlay).
#
# Fail-loud: a SIF without scitex-dev baked is a hard error (rebuild the SIF).
set -euo pipefail

V="${1:?python version arg required (3.11/3.12/3.13)}"
VENV="/opt/venv-$V"
test -x "$VENV/bin/scitex-dev" || {
    echo "::error::baked scitex-dev console script missing in $VENV — rebuild: scitex-container apptainer build ci-cpu"
    exit 1
}

export LC_ALL=C.UTF-8 LANG=C.UTF-8

# Real writable scratch. The runner profile exports TMPDIR=~/.cache/tmp, a host
# path that does NOT resolve inside the container; tests (tmp_path) and mktemp
# need a working tmp. Node-local /tmp is writable + ephemeral.
export TMPDIR="/tmp/ci-$V"
mkdir -p "$TMPDIR"

# A VIRTUAL_ENV leaked from the runner profile (~/.env-3.11) is a broken symlink
# in here; unset it so no tool (uv, pip) tries to follow it.
unset VIRTUAL_ENV || true

# venv bin on PATH (python3, pytest, the baked scitex-dev console script);
# PYTHONPATH prepends the checkout so imports + coverage use the PR code.
export PATH="$VENV/bin:$PATH"
export PYTHONPATH="$PWD/src"

echo "py=$("$VENV"/bin/python -V) scitex-dev=$(command -v scitex-dev) ver=$(scitex-dev --version 2>&1 | head -1)"
# Parallelise across ALL cores of the Spartan CPU lease (64-core node). The
# baked SIF supplies pytest-xdist; -n "$(nproc)" uses every allocated core and
# --dist loadscope groups tests by module/class onto one worker so module-scoped
# fixtures + setup_module run once per worker (not per test) — the figrecipe gold
# pattern. coverage already runs parallel=true (see [tool.coverage.run]) so the
# per-worker .coverage.* shards merge cleanly.
echo "xdist workers (nproc): $(nproc)"
exec pytest tests/ -n "$(nproc)" --dist loadscope --cov=src/scitex_dev --cov-report=xml --cov-report=term
