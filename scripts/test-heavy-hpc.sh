#!/usr/bin/env bash
# Dispatch heavy SciTeX test suites to a remote HPC cluster via scitex-hpc.
#
# This script is generic. All site-specific values (host, partition, package
# list) live in ~/.scitex/hpc/config.yaml — see that file for the schema.
#
# Why: GitHub-hosted runners (2-core, 7 GB RAM) are slow for packages with
# hundreds of tests + heavy deps (torch, mne, etc). A 32-core CPU node with
# `pytest -n 16` finishes in a fraction of the time. Login nodes never run
# compute — every `pytest` goes through srun via scitex_hpc.
#
# Usage:
#   ./scripts/test-heavy-hpc.sh                       # all heavy pkgs from config
#   ./scripts/test-heavy-hpc.sh scitex-dsp scitex-nn  # subset
#   COVERAGE=1 ./scripts/test-heavy-hpc.sh            # with --cov
#   FAST=1 ./scripts/test-heavy-hpc.sh                # skip slow tests
#
# Requirements:
#   - ~/.scitex/hpc/config.yaml exists with `host`, `partition`, `heavy_packages`
#   - `ssh <host>` works without prompt (key + agent)
#   - Each package is rsync'd to ~/proj/<pkg> on the remote (use spartan-nightly.sh
#     or `scitex_hpc.sync` first if stale).

set -euo pipefail

CONFIG="${SCITEX_HPC_CONFIG:-${HOME}/.scitex/hpc/config.yaml}"
[[ -f "${CONFIG}" ]] || {
    echo "missing ${CONFIG} — see scitex-dev/scripts/README.md" >&2
    exit 2
}

# Read host / partition / cpus / package list from yaml via Python.
read -r HOST PARTITION CPUS DEFAULT_PKGS < <(
    python3 - <<PY
import yaml, sys
cfg = yaml.safe_load(open("${CONFIG}"))
host = cfg.get("host", "")
part = cfg.get("partition", "")
cpus = cfg.get("cpus_per_task", 16)
pkgs = " ".join(cfg.get("heavy_packages", []))
print(host, part, cpus, pkgs)
PY
)

if [[ $# -gt 0 ]]; then
    PACKAGES=("$@")
else
    # shellcheck disable=SC2206
    PACKAGES=(${DEFAULT_PKGS})
fi
COVERAGE=${COVERAGE:-0}
FAST=${FAST:-0}

for pkg in "${PACKAGES[@]}"; do
    echo "=== ${pkg} on ${HOST}/${PARTITION} ==="
    if ! python3 - <<PY; then
from scitex_hpc import JobConfig, srun
import sys
pytest_cmd = (
    'pip install -e ".[dev]" -q && '
    'python -m pytest tests/ -n ${CPUS} --dist loadfile --tb=short'
    + (' --cov --cov-report=term-missing' if ${COVERAGE} == 1 else '')
    + (" -m 'not slow'" if ${FAST} == 1 else '')
)
cfg = JobConfig(
    project='${pkg}',
    command=pytest_cmd,
    host='${HOST}',
    partition='${PARTITION}' or None,
    cpus=${CPUS},
)
sys.exit(srun(cfg))
PY
        echo "FAILED: ${pkg}" >&2
    fi
done
