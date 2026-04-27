#!/usr/bin/env bash
# Dispatch the heavy SciTeX test suites to Spartan's sapphire CPU nodes.
#
# Why: GitHub-hosted runners (2-core, 7 GB RAM) make pytest slow and flaky
# for packages with hundreds of tests + heavy deps (torch, mne, etc).
# Spartan's sapphire partition has 32-core nodes — `pytest -n 32` finishes
# in a fraction of the time and with parallelism the ecosystem actually
# needs. Login node never runs compute — every `pytest` goes through srun.
#
# Usage:
#   ./scripts/test-heavy-on-spartan.sh                 # all heavy pkgs
#   ./scripts/test-heavy-on-spartan.sh scitex-dsp scitex-nn   # subset
#   COVERAGE=1 ./scripts/test-heavy-on-spartan.sh      # with --cov
#   FAST=1 ./scripts/test-heavy-on-spartan.sh          # skip slow tests
#
# Requirements:
#   - `ssh spartan` works without prompt (key + agent)
#   - `~/.scitex/dev/config.yaml` has spartan host configured (it does)
#   - Each package is rsync'd to `~/proj/<pkg>` on Spartan
#     (run `scitex-dev sync --host spartan -p <pkg>` first if stale)

set -euo pipefail

HEAVY_PACKAGES_DEFAULT=(
    scitex-cloud   # 620 tests
    scitex-io      # 81 tests + heavy ports
    scitex-scholar # 22 tests + network heavy
    scitex-nn      # torch, julius, torchaudio
    scitex-dsp     # torch, scipy, mne
    scitex-gen     # torch, h5py, matplotlib
    scitex-stats   # statsmodels, mcp
    figrecipe      # 51 tests + matplotlib heavy
    scitex-writer  # latex toolchain
    scitex-db      # 47 tests + sqlite/postgres
)

PACKAGES=("${@:-${HEAVY_PACKAGES_DEFAULT[@]}}")
COVERAGE=${COVERAGE:-0}
FAST=${FAST:-0}

for pkg in "${PACKAGES[@]}"; do
    echo "=== ${pkg} on spartan/sapphire ==="
    if ! python3 -c "
from scitex_hpc import JobConfig, srun
import sys
pytest_cmd = (
    'pip install -e \".[dev]\" -q && '
    'python -m pytest tests/ -n 16 --dist loadfile --tb=short'
    + (' --cov --cov-report=term-missing' if ${COVERAGE} == 1 else '')
    + (\" -m 'not slow'\" if ${FAST} == 1 else '')
)
cfg = JobConfig(project='${pkg}', command=pytest_cmd, host='spartan')
sys.exit(srun(cfg))
"; then
        echo "FAILED: ${pkg}" >&2
    fi
done
