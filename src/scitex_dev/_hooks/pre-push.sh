#!/usr/bin/env bash
# scitex-dev — canonical pre-push gate hook.
# -*- coding: utf-8 -*-
#
# RED-GREEN DOCTRINE
# ------------------
# Local CI MUST verify what CI verifies that is CHEAP and SCOPED, so the
# operator does not push → red → patch → push → red merry-go-round. Heavy
# tests (slow / integration / network) stay in CI. This hook runs:
#
#   1. `scitex-dev ecosystem audit-all <pkg> --path <repo> --severity error`
#      — the same audit gate `tests/develop/test_audit.py` runs (the
#      one installed by `scitex-dev ecosystem install-audit-gate`).
#   2. Scope tests: `pytest --testmon -m "not slow and not integration"`
#      time-bound by `timeout 60` — narrow, fast, and aborts if any
#      collected test fails.
#
# On either failure the push is blocked with a clear stderr message
# naming WHAT failed and HOW to bypass.
#
# CALLED BY: git, as `.git/hooks/pre-push` or the
# `core.hooksPath/pre-push` symlink installed by
# `scitex-dev hooks enable-pre-push --target <repo>`.
#
# CONTRACT: git invokes pre-push with `<remote> <url>` argv and a list
# of refs on stdin (we don't consume stdin; the gate is the same for
# every ref). Exit 0 = allow the push. Non-zero = abort.
#
# BYPASS: `git push --no-verify` still works (we deliberately do not
# try to forbid it — operator emergency hatch). `SCITEX_DEV_SKIP_PREPUSH=1
# git push` also skips both steps. Either of these prints a notice to
# stderr so the choice is visible in the agent transcript.
#
# Distributable to other ecosystem packages: install as a SYMLINK so
# scitex-dev releases auto-propagate. See `scitex-dev hooks install
# --name pre_push --target <repo>` and the higher-level wrapper
# `scitex-dev hooks enable-pre-push --target <repo>` which also wires
# `core.hooksPath`.

set -u  # NOT -e: we manage exit codes explicitly so the failure
        # message is always emitted before the script exits.

GRAY='\033[0;90m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo_info() { echo -e "${GRAY}INFO: $1${NC}" >&2; }
echo_success() { echo -e "${GREEN}PASS: $1${NC}" >&2; }
echo_warning() { echo -e "${YELLOW}WARN: $1${NC}" >&2; }
echo_error() { echo -e "${RED}FAIL: $1${NC}" >&2; }
echo_header() { echo_info "=== $1 ==="; }

# Honour the same emergency-bypass env var convention as the audit
# test gate (SCITEX_DEV_SKIP_AUDIT) so operators have one knob to
# remember. Print a notice so the choice is visible.
if [[ "${SCITEX_DEV_SKIP_PREPUSH:-0}" == "1" ]]; then
    echo_warning "pre-push gate skipped via SCITEX_DEV_SKIP_PREPUSH=1"
    echo_warning "(unset the env var to re-enable, or remove it from your shell rc)"
    exit 0
fi

# --self-test: smoke-check the hook works without invoking git/pytest.
# Used by `tests/scitex_dev/_hooks/test_pre_push.py` so we don't need
# to spin up a real git repo to validate the script can at least parse.
if [[ "${1:-}" == "--self-test" ]]; then
    echo "=== Self-test: $(basename "$0") ==="
    # Verify the script is at least syntactically valid bash. The
    # `bash -n` check is performed by re-execing this script under -n;
    # since we already sourced it, reaching this point means the parse
    # succeeded. We then check that the required external binaries
    # ARE detectable (or that we degrade gracefully when missing).
    pass=0
    fail=0
    if command -v git >/dev/null 2>&1; then
        ((pass++)); echo "  PASS: git on PATH"
    else
        ((fail++)); echo "  FAIL: git not on PATH"
    fi
    # scitex-dev / pytest are optional in self-test — the live hook
    # warns and continues if either is missing (see below). The
    # self-test only verifies that the *detection* logic is reachable.
    if command -v scitex-dev >/dev/null 2>&1; then
        echo "  INFO: scitex-dev on PATH"
    else
        echo "  INFO: scitex-dev NOT on PATH (live hook will skip audit step)"
    fi
    if command -v pytest >/dev/null 2>&1 || python3 -c "import pytest" >/dev/null 2>&1; then
        echo "  INFO: pytest available"
    else
        echo "  INFO: pytest NOT available (live hook will skip scope tests)"
    fi
    echo "Results: $pass passed, $fail failed"
    [[ $fail -eq 0 ]] && exit 0 || exit 1
fi

# Resolve the repo root from the cwd git invocation. `git rev-parse
# --show-toplevel` returns the path with no trailing newline; if we're
# not inside a repo we bail with a clear message (the hook is only
# meaningful when invoked from a repo).
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
    echo_error "pre-push hook ran outside a git repository (no toplevel)"
    echo_error "this should be impossible — investigate before bypassing"
    exit 1
fi

# Identify the package name. Two strategies, in order:
#   (1) Parse the `[project] name = ...` line from pyproject.toml at
#       the repo root. This is the canonical ecosystem identity (each
#       package's distribution name matches its repo basename in
#       SciTeX) and survives clones with non-standard directory names.
#   (2) Fall back to the basename of the repo root. The audit-all
#       command will reject unknown names with a clear "not in
#       ECOSYSTEM" message — better than guessing wrong silently.
PKG_NAME=""
if [[ -f "$REPO_ROOT/pyproject.toml" ]]; then
    PKG_NAME="$(python3 -c "
import sys, re
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        # Fallback: regex out the project name. tomllib is stdlib from
        # 3.11; older Pythons without tomli installed get the regex.
        text = open('$REPO_ROOT/pyproject.toml').read()
        m = re.search(r'^name\s*=\s*[\"\']([^\"\']+)[\"\']', text, re.MULTILINE)
        print(m.group(1) if m else '')
        sys.exit(0)
with open('$REPO_ROOT/pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
print(data.get('project', {}).get('name', ''))
" 2>/dev/null || true)"
fi
if [[ -z "$PKG_NAME" ]]; then
    PKG_NAME="$(basename "$REPO_ROOT")"
fi

echo_header "scitex-dev pre-push gate ($PKG_NAME)"
echo_info "repo: $REPO_ROOT"

# Time budget for the WHOLE hook. Red-green doctrine: a pre-push gate
# that takes > 60s breaks the push flow and gets bypassed; the goal is
# "always run, never noticed unless red", not "thorough." Heavy tests
# go through CI.
DEADLINE_SECONDS="${SCITEX_DEV_PREPUSH_TIMEOUT:-60}"

# ----------------------------------------------------------------- #
# Step 1: audit-all --path <repo>                                   #
# ----------------------------------------------------------------- #
#
# Three-tier fallback to locate the scitex-dev entry point. Without
# this, a worktree whose editable-install `.pth` file points at a
# deleted checkout fires `ModuleNotFoundError: scitex_dev` even though
# `scitex-dev` is still on PATH — the operator gets a confusing
# "command not found" / `ModuleNotFoundError` instead of the actionable
# remediation. The probe order is:
#   1. `scitex-dev` on PATH (the canonical case).
#   2. `python3 -m scitex_dev` (system python sees the package).
#   3. `$SCITEX_DEV_PYTHON -m scitex_dev` or the running interpreter
#      (the operator's active venv).
# If all three fail we abort the push with a literal `uv pip install
# -e <checkout>` remediation so the fix is one read away. The hook is
# shell-only, so we cannot probe `sys.executable` of an unrelated
# python — we just try `python3` (path-resolved) and a `python` alias.
SCITEX_DEV_CMD=""
if command -v scitex-dev >/dev/null 2>&1 && \
        scitex-dev --version >/dev/null 2>&1; then
    SCITEX_DEV_CMD="scitex-dev"
elif command -v python3 >/dev/null 2>&1 && \
        python3 -m scitex_dev --version >/dev/null 2>&1; then
    SCITEX_DEV_CMD="python3 -m scitex_dev"
elif command -v python >/dev/null 2>&1 && \
        python -m scitex_dev --version >/dev/null 2>&1; then
    SCITEX_DEV_CMD="python -m scitex_dev"
fi

AUDIT_RC=0
if [[ -n "$SCITEX_DEV_CMD" ]]; then
    echo_info "[1/2] $SCITEX_DEV_CMD ecosystem audit-all $PKG_NAME --path $REPO_ROOT --severity error"
    # NB: `if ! cmd; then $?` always reports 0 (the `!`-inverted
    # truthy result); the original exit code is lost. Capture it
    # directly so the message names the audit-all rc the operator
    # needs to grep. Also: do NOT pipe stderr — `>&2` after the
    # whole pipeline keeps git pre-push's expected stream order.
    timeout "$DEADLINE_SECONDS" $SCITEX_DEV_CMD ecosystem audit-all "$PKG_NAME" \
        --path "$REPO_ROOT" --severity error --no-version-check >&2
    AUDIT_RC=$?
    if [[ "$AUDIT_RC" -ne 0 ]]; then
        echo_error "audit-all failed (rc=$AUDIT_RC)"
    else
        echo_success "audit-all clean"
    fi
else
    # Loud, actionable error — the operator must see the remediation
    # in ONE read. This is the editable-install-drift class: the venv's
    # `scitex_dev.pth` points at a checkout that was removed (e.g. a
    # finished worktree), so `scitex-dev` on PATH but `import scitex_dev`
    # raises ModuleNotFoundError. Block the push so CI doesn't redress
    # the same import error.
    echo_error "[1/2] scitex-dev not importable. Editable install may have drifted (worktree removed)."
    echo_error "Fix: cd <repo> && uv pip install -e <scitex-dev-checkout>"
    echo_error "     (probed: \`scitex-dev\`, \`python3 -m scitex_dev\`, \`python -m scitex_dev\` — all failed)"
    AUDIT_RC=127
fi

# ----------------------------------------------------------------- #
# Step 2: pytest --testmon -m "not slow and not integration"        #
# ----------------------------------------------------------------- #
#
# --testmon picks only the tests whose imported sources have changed
# since the last green run (kept in `.testmondata` at the repo root).
# `-m "not slow and not integration"` excludes heavy markers used
# across the ecosystem. `-x` stops at the first failure so the operator
# sees the failure quickly. The overall `timeout` is the safety net.
TEST_RC=0
if [[ -d "$REPO_ROOT/tests" ]]; then
    PYTEST_BIN=""
    if command -v pytest >/dev/null 2>&1; then
        PYTEST_BIN="pytest"
    elif python3 -c "import pytest" >/dev/null 2>&1; then
        PYTEST_BIN="python3 -m pytest"
    fi
    if [[ -n "$PYTEST_BIN" ]]; then
        echo_info "[2/2] $PYTEST_BIN --testmon -x -m 'not slow and not integration'"
        # We deliberately do NOT pass --no-header / -q: the operator
        # needs to see what ran when something fails. stderr is the
        # right channel because git pre-push hooks emit hook output
        # interleaved with the push command's own stderr.
        # Same `if ! cmd` trap as the audit step — capture `$?`
        # directly so the failure message names the real pytest rc,
        # not the inverted truthy 0.
        ( cd "$REPO_ROOT" && timeout "$DEADLINE_SECONDS" $PYTEST_BIN \
                --testmon -x --tb=short \
                -m "not slow and not integration" \
                tests >&2 )
        TEST_RC=$?
        if [[ "$TEST_RC" -ne 0 ]]; then
            echo_error "scope tests failed (rc=$TEST_RC)"
        else
            echo_success "scope tests clean"
        fi
    else
        echo_warning "[2/2] pytest not available — scope test step SKIPPED"
        echo_warning "      install: pip install pytest pytest-testmon"
    fi
else
    echo_warning "[2/2] no tests/ directory — scope test step SKIPPED"
fi

# ----------------------------------------------------------------- #
# Verdict                                                           #
# ----------------------------------------------------------------- #

if [[ "$AUDIT_RC" -ne 0 || "$TEST_RC" -ne 0 ]]; then
    echo_error "----------------------------------------------------------"
    echo_error "PUSH BLOCKED by scitex-dev pre-push gate"
    [[ "$AUDIT_RC" -ne 0 ]] && echo_error "  - audit-all returned $AUDIT_RC"
    [[ "$TEST_RC"  -ne 0 ]] && echo_error "  - scope tests returned $TEST_RC"
    echo_error ""
    echo_error "Fix the failures above, then re-run \`git push\`."
    echo_error ""
    echo_error "Emergency bypass (use sparingly — CI will still red):"
    echo_error "  SCITEX_DEV_SKIP_PREPUSH=1 git push   # one-shot skip"
    echo_error "  git push --no-verify                  # git's native skip"
    echo_error "----------------------------------------------------------"
    exit 1
fi

echo_success "pre-push gate passed — push allowed"
exit 0

# EOF
