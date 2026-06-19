#!/usr/bin/env bash
# Outer wrapper — runs ON the self-hosted Spartan runner (NOT in the SIF).
# Locates apptainer + the reused CI SIF, then execs run-in-sif.sh inside it.
# All args are forwarded to run-in-sif.sh (e.g. `pytest 3.12`, `audit`).
# IDENTICAL across every repo; package-agnostic.
#
# fail-loud: a missing apptainer shim or a missing SIF is a hard error.
set -euo pipefail

# The runner job shell is --noprofile --norc (no Lmod); the self-contained
# apptainer shim execs the real Apptainer binary without a login shell.
export PATH="$HOME/.env-3.11/bin:$PATH"
command -v apptainer >/dev/null || {
    echo "::error::apptainer shim not on PATH (~/.env-3.11/bin)"
    exit 1
}

IMG="$HOME/.scitex/dev/containers/ci-cpu.sif"
[ -f "$IMG" ] || {
    echo "::error::CI SIF missing at $IMG — rebuild: scitex-container apptainer build ci-cpu"
    exit 1
}

# apptainer scratch on punim0264 — HOME stays clean.
export APPTAINER_TMPDIR=/data/gpfs/projects/punim0264/ywatanabe/ci/apptainer-tmp
mkdir -p "$APPTAINER_TMPDIR"

# --bind punim0264: ~/.scitex symlinks into it; bind so the symlink resolves
# inside the container (scitex_logging's on-import log-dir mkdir needs it).
exec apptainer exec --pwd "$PWD" --bind /data/gpfs/projects/punim0264 \
    "$IMG" bash .github/ci/run-in-sif.sh "$@"
