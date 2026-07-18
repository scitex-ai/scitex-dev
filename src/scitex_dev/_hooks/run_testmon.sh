#!/usr/bin/env bash
# scitex-dev — canonical pytest-testmon warm-cache wrapper.
# -*- coding: utf-8 -*-
#
# This is the AUTHORITATIVE source for the testmon PRE-PUSH selector.
# It makes pytest-testmon worktree-resilient via a persistent per-repo
# warm cache. Its sole in-fleet caller is the pre-push gate (`pre-push.sh`
# Step 4), which invokes it so a fresh release worktree gets the warm
# cache instead of cold-running the full suite. This is NOT a
# `.pre-commit-config.yaml` entry: a test selector belongs at pre-push,
# not pre-commit (see 15_pre-commit-policy.md).
#
# THE PROBLEM IT SOLVES
# ---------------------
# Every SciTeX release runs in a FRESH git worktree (forced by the
# develop-pin hook), so the worktree's ``.testmondata`` is always COLD.
# testmon then has no impact graph and re-runs the FULL ~2500-test suite
# (~2h) instead of only the tests touched by the diff. A persistent
# cache shared across worktrees fixes this: we seed-copy a warm
# ``.testmondata`` into the worktree before pytest runs, then write the
# updated DB back to the cache afterwards.
#
# (repo, pyXY) KEYING
# -------------------
# testmon invalidates its DB whenever the interpreter / dependency
# fingerprint changes, so we MUST NOT let two python versions share one
# file. The cache path is keyed by both repo name and ``py<major><minor>``
# (e.g. ``py312``) so each (repo, interpreter) pair owns its own DB.
#
# CACHE ROOT
# ----------
# ``SCITEX_TESTMON_CACHE_ROOT`` is injected by the sac container
# (=/home/agent/.cache/scitex-testmon). The ``$HOME/.cache/...`` default
# covers local / non-container dev.
#
# WIRING
# ------
# The pre-push gate resolves this script's absolute path via
#
#     scitex-dev hooks show-path run_testmon
#
# and calls it as the Step-4 test selector, so future fixes land here and
# every project's pre-push gate picks them up. (A `scitex-dev-testmon`
# console script also execs this wrapper for callers that need a bare,
# shell-expansion-free entry point.)

set -euo pipefail

# ---------------------------------------------------------------------- #
# Deterministic interpreter resolution                                   #
# ---------------------------------------------------------------------- #
# Resolve the Python interpreter to an ABSOLUTE path ONCE, up front, and
# use it for every `python`/`pytest` invocation below. A bare `python3`
# off the ambient $PATH is exactly the PS-HOOK-001 anti-pattern (the
# $PATH lottery that resolves to a different venv per machine) — this
# wrapper must not itself commit it. Precedence:
#   1. $SCITEX_DEV_PYTHON — explicit operator/CI override.
#   2. `command -v python3` — the active PATH's python3, captured to an
#      absolute path (so the recorded argv[0] contains a `/`, not a bare
#      name), resolved deterministically for the whole run.
# Fail LOUDLY if neither resolves — a silent skip would let a cold suite
# masquerade as a warm-cache run.
PY="${SCITEX_DEV_PYTHON:-}"
if [[ -z "$PY" ]]; then
    PY="$(command -v python3 || true)"
fi
if [[ -z "$PY" ]]; then
    echo "run_testmon.sh: no python3 interpreter found on PATH." >&2
    echo "run_testmon.sh: set SCITEX_DEV_PYTHON to an absolute interpreter." >&2
    exit 127
fi

# --self-test: verify the cache-path resolution logic runs without a real
# pytest by short-circuiting before the RUN stage. Mirrors run_lint.sh.
if [[ "${1:-}" == "--self-test" ]]; then
    echo "=== Self-test: $(basename "$0") ==="
    pass=0
    fail=0

    GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    # Use --git-common-dir (not --show-toplevel) to derive REPO: inside a
    # worktree, --show-toplevel returns the WORKTREE's own directory (e.g.
    # figrecipe/.worktrees/fix-coverage-pth), so basename yields the
    # worktree's name, not the repo's -- keying the persistent cache by a
    # different value per worktree and defeating the whole point of sharing
    # it. --git-common-dir always resolves to the shared .git dir regardless
    # of which worktree invoked this script.
    GIT_COMMON_DIR="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo "$GIT_ROOT/.git")"
    REPO="$(basename "$(dirname "$GIT_COMMON_DIR")")"
    PYXY="$("$PY" -c 'import sys;print(f"py{sys.version_info.major}{sys.version_info.minor}")')"
    CACHE_ROOT="${SCITEX_TESTMON_CACHE_ROOT:-$HOME/.cache/scitex-testmon}"
    CACHE_DIR="$CACHE_ROOT/$REPO/$PYXY"

    if [[ -n "$REPO" ]]; then
        pass=$((pass + 1))
        echo "  PASS: repo resolved ($REPO)"
    else
        fail=$((fail + 1))
        echo "  FAIL: repo did not resolve"
    fi
    if [[ "$PYXY" =~ ^py[0-9]+$ ]]; then
        pass=$((pass + 1))
        echo "  PASS: interpreter key resolved ($PYXY)"
    else
        fail=$((fail + 1))
        echo "  FAIL: interpreter key malformed ($PYXY)"
    fi
    if [[ "$CACHE_DIR" == */"$REPO"/"$PYXY" ]]; then
        pass=$((pass + 1))
        echo "  PASS: cache dir keyed by (repo, pyXY) ($CACHE_DIR)"
    else
        fail=$((fail + 1))
        echo "  FAIL: cache dir not keyed correctly ($CACHE_DIR)"
    fi

    # Regression guard: if we're inside a linked worktree (path contains
    # /.worktrees/<name>), REPO must NOT equal the worktree's own directory
    # name -- that was exactly the bug this fix closes. Only meaningful when
    # actually run from inside such a path, so this is a no-op elsewhere.
    if [[ "$GIT_ROOT" == *"/.worktrees/"* ]]; then
        worktree_name="$(basename "$GIT_ROOT")"
        if [[ "$REPO" != "$worktree_name" ]]; then
            pass=$((pass + 1))
            echo "  PASS: worktree-invariant (REPO=$REPO != worktree dir=$worktree_name)"
        else
            fail=$((fail + 1))
            echo "  FAIL: REPO leaked the worktree dir name ($REPO) -- cache no longer shared across worktrees"
        fi
    fi

    echo "Results: $pass passed, $fail failed"
    [[ $fail -eq 0 ]] && exit 0 || exit 1
fi

# Resolve the worktree root, repo name, and interpreter key.
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# See the matching --self-test block above for why REPO is derived from
# --git-common-dir rather than GIT_ROOT/--show-toplevel.
GIT_COMMON_DIR="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo "$GIT_ROOT/.git")"
REPO="$(basename "$(dirname "$GIT_COMMON_DIR")")"
PYXY="$("$PY" -c 'import sys;print(f"py{sys.version_info.major}{sys.version_info.minor}")')"

CACHE_ROOT="${SCITEX_TESTMON_CACHE_ROOT:-$HOME/.cache/scitex-testmon}"
CACHE_DIR="$CACHE_ROOT/$REPO/$PYXY"
CACHE_FILE="$CACHE_DIR/.testmondata"
LOCAL_FILE="$GIT_ROOT/.testmondata"

# SEED-IN: warm the worktree's cold DB from the persistent cache.
if [[ -f "$CACHE_FILE" ]]; then
    cp -f "$CACHE_FILE" "$LOCAL_FILE" 2>/dev/null || true
fi

# RUN: pytest returns non-zero on test failures; capture the code WITHOUT
# letting `set -e` abort before the write-back stage runs. `$PY` is the
# absolute interpreter resolved up top — never a bare `python3` off $PATH.
set +e
"$PY" -m pytest --testmon "$@"
rc=$?
set -e

# WRITE-BACK: persist the freshly-updated DB only when tests actually ran
# (rc 0 = all pass, rc 1 = test failures — both yield a valid DB). rc>=2
# means interrupted / usage / internal error, so we skip to never cache a
# broken state.
if [[ -f "$LOCAL_FILE" && "$rc" -lt 2 ]]; then
    mkdir -p "$CACHE_DIR" 2>/dev/null || true
    cp -f "$LOCAL_FILE" "$CACHE_FILE" 2>/dev/null || true
fi

exit $rc

# EOF
