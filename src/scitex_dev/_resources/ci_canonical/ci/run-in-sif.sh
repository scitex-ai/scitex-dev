#!/usr/bin/env bash
# Canonical CI entrypoint — runs INSIDE the reused CI SIF (apptainer exec).
# IDENTICAL across every scitex ecosystem repo (synced by
# `scitex-dev ecosystem sync-workflows`); package-agnostic — it derives the
# import package + distribution name from the checkout, so there is nothing to
# substitute per repo.
#
# Usage: run-in-sif.sh <mode> [python-version]
#   modes:  pytest <ver> | import-smoke | audit | docs
#
# The SIF (~/.scitex/dev/containers/ci-cpu.sif) is READ-ONLY and bakes the
# ecosystem dependency set in /opt/venv-3.{11,12,13}. CI must run the
# CHECKOUT's code, so PYTHONPATH prepends $PWD/src — that shadows any baked
# copy for imports + coverage. No install, no --writable-tmpfs.
#
# fail-loud / no silent fallbacks: a missing baked venv or a missing package is
# a hard error, never a reinstall fallback.
set -euo pipefail

MODE="${1:?mode required: pytest|import-smoke|audit|docs}"

# --- Derive package (import name) + distribution (PyPI name) from the checkout.
PKG="$(basename "$(find src -maxdepth 1 -mindepth 1 -type d ! -name '*.egg-info' | sort | head -1)")"
[ -n "$PKG" ] || {
    echo "::error::no package directory under src/"
    exit 1
}
DIST="$(python3 -c "import tomllib,sys; print(tomllib.load(open('pyproject.toml','rb'))['project']['name'])" 2>/dev/null || echo "${PKG//_/-}")"

export LC_ALL=C.UTF-8 LANG=C.UTF-8
export TMPDIR="/tmp/ci-${PKG}-${2:-x}"
mkdir -p "$TMPDIR"
unset VIRTUAL_ENV || true    # a leaked runner VIRTUAL_ENV is a broken symlink in here
export PYTHONPATH="$PWD/src" # the checkout's code wins for imports + coverage

_use_venv() { # $1 = python version (defaults to 3.12)
    local venv="/opt/venv-${1:-3.12}"
    test -x "$venv/bin/python" || {
        echo "::error::baked venv python missing in $venv — rebuild: scitex-container apptainer build ci-cpu"
        exit 1
    }
    export PATH="$venv/bin:$PATH"
}

case "$MODE" in
pytest)
    V="${2:?python version arg required (3.11/3.12/3.13)}"
    _use_venv "$V"
    echo "py=$(python -V) pkg=$PKG dist=$DIST"
    exec pytest tests/ --cov="src/$PKG" --cov-report=xml --cov-report=term
    ;;
import-smoke)
    _use_venv 3.12
    echo "import-smoke pkg=$PKG"
    exec python -c "import importlib; m=importlib.import_module('$PKG'); print('import OK:', m.__name__)"
    ;;
audit)
    _use_venv 3.12
    # Audit the CHECKOUT (workspace), never a baked/shared copy — `--path .`
    # is what makes the gate depend on the PR code, not the runner's state.
    echo "audit dist=$DIST path=$PWD"
    exec scitex-dev ecosystem audit-all "$DIST" --path "$PWD"
    ;;
docs)
    _use_venv 3.12
    test -d docs || {
        echo "no docs/ — skipping sphinx"
        exit 0
    }
    exec python -m sphinx -b html -W --keep-going docs docs/_build/html
    ;;
*)
    echo "::error::unknown mode '$MODE'"
    exit 1
    ;;
esac
