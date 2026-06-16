#!/usr/bin/env bash
# Runs INSIDE the reused CI SIF (apptainer exec). $1 = python version.
#
# The SIF is read-only and DEPS-ONLY (scitex-dev itself is NOT baked), so we
# add the checkout without any pip install / --writable-tmpfs — nothing is
# ever written into the SIF:
#   - import path        : PYTHONPATH=$PWD/src (the checked-out package)
#   - `python3` + pytest : the baked venv's bin on PATH
#   - `scitex-dev` cmd   : a tiny console-script shim (entry scitex_dev._cli:main)
#
# Fail-loud: a missing baked venv is a hard error (rebuild the SIF), never a
# silent reinstall fallback.
set -euo pipefail

V="${1:?python version arg required (3.11/3.12/3.13)}"
VENV="/opt/venv-$V"
test -x "$VENV/bin/python" || {
    echo "::error::baked venv $VENV missing in the SIF — rebuild: scitex-container apptainer build ci-cpu"
    exit 1
}

export LC_ALL=C.UTF-8 LANG=C.UTF-8

# Real writable scratch. The runner profile exports TMPDIR=~/.cache/tmp, a
# host path that does NOT resolve inside the container; tests (tmp_path) and
# mktemp need a working tmp. Node-local /tmp is writable + ephemeral.
export TMPDIR="/tmp/ci-$V"
mkdir -p "$TMPDIR"

# A VIRTUAL_ENV leaked from the runner profile (~/.env-3.11) is a broken
# symlink in here; unset it so no tool (uv, pip) tries to follow it.
unset VIRTUAL_ENV || true

# Console-script shim: `scitex-dev` is a click group (entry scitex_dev._cli:main,
# pinned by PS-213). Absolute-python shebang so it needs nothing on PATH;
# `audit-all` copies os.environ into its sub-audit subprocesses, so the
# PYTHONPATH below propagates to them too.
WBIN="$TMPDIR/bin"
mkdir -p "$WBIN"
cat >"$WBIN/scitex-dev" <<EOF
#!$VENV/bin/python
import sys
from scitex_dev._cli import main
sys.exit(main())
EOF
chmod +x "$WBIN/scitex-dev"

# shim first (scitex-dev), then the baked venv bin (python3, pytest).
export PATH="$WBIN:$VENV/bin:$PATH"
export PYTHONPATH="$PWD/src"

echo "py=$("$VENV"/bin/python -V) python3=$(command -v python3) scitex-dev=$(command -v scitex-dev)"
exec pytest tests/ --cov=src/scitex_dev --cov-report=xml --cov-report=term
