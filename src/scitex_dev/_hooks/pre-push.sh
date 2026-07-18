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
#   2. `ruff check --select F401,F811` on CHANGED .py files only.
#      F401 = unused import, F811 = redefined-while-unused. Cheap,
#      diff-scoped, catches the lint regressions that bite CI most often.
#   3. `import-smoke`: import every CHANGED module under `src/` to catch
#      the "wheel installs but runtime ImportError" class. Diff-scoped.
#   4. Scope tests: the `run_testmon` warm-cache wrapper (resolved via
#      `scitex-dev hooks show-path run_testmon`) running `pytest --testmon
#      -m "not slow and not integration"`, time-bound by `timeout 60` —
#      narrow, fast, and aborts if any collected test fails. Routing
#      through the wrapper (not a bare `pytest --testmon`) seeds the
#      persistent per-(repo,pyXY) `.testmondata` cache so a FRESH release
#      worktree runs only impacted tests instead of cold-running the full
#      suite, and pins an absolute interpreter (no ambient-$PATH lottery).
#
# DIFF SCOPING (key design principle):
# All steps that CAN be scoped to `git diff` ARE scoped. Steps 2 + 3 work
# on the changed-file list (`git diff --name-only --diff-filter=AM
# @{upstream}..HEAD -- '*.py'` with a fallback to ORIGIN/HEAD when no
# upstream is set). Step 4 (testmon) is already diff-aware. Step 1
# (audit-all) is whole-repo today — scoping is tracked separately.
#
# Heavy CI items remain CI-only by design: pytest-matrix (3.11/3.12/3.13),
# sphinx-docs, codecov upload, ecosystem-audit whole-repo. The gate is the
# fast subset; CI is the thorough subset.
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
# Used by `tests/scitex_dev/_hooks/test___init___pre_push.py` so we don't need
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
# Diff scope: list .py files changed since the upstream tracking    #
# branch (or origin/HEAD as a fallback). Used by the ruff + import-  #
# smoke steps so they are O(diff), not O(repo).                     #
# ----------------------------------------------------------------- #
#
# We probe the diff range in this order:
#   1. `@{upstream}..HEAD` — the canonical "what am I about to push"
#      when the local branch tracks a remote.
#   2. `origin/HEAD..HEAD` — fallback when no upstream is set yet
#      (e.g. brand-new feature branch never pushed).
#   3. Empty list — degrades gracefully: ruff + import-smoke become
#      no-ops with an INFO message. Better than failing loud on a
#      fresh checkout.
#
# Filters:
#   --diff-filter=AM — Added or Modified (skip Deleted / Renamed-only)
#   -- '*.py'        — Python sources only
#
# The list is exported as $CHANGED_PY (newline-separated, may be empty).
CHANGED_PY=""
DIFF_RANGE=""
if git -C "$REPO_ROOT" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' \
        >/dev/null 2>&1; then
    DIFF_RANGE='@{upstream}..HEAD'
elif git -C "$REPO_ROOT" rev-parse --verify origin/HEAD >/dev/null 2>&1; then
    DIFF_RANGE='origin/HEAD..HEAD'
fi
if [[ -n "$DIFF_RANGE" ]]; then
    # `git diff --name-only` with a range is silent on errors; capture
    # and filter to existing files (a rename leftover could otherwise
    # name a path that no longer exists on disk and confuse ruff).
    CHANGED_PY="$(
        git -C "$REPO_ROOT" diff --name-only --diff-filter=AM \
            $DIFF_RANGE -- '*.py' 2>/dev/null \
            | while IFS= read -r f; do
                [[ -f "$REPO_ROOT/$f" ]] && echo "$f"
            done
    )"
fi
CHANGED_PY_COUNT=0
if [[ -n "$CHANGED_PY" ]]; then
    CHANGED_PY_COUNT="$(echo "$CHANGED_PY" | wc -l | tr -d ' ')"
fi
echo_info "diff scope: $CHANGED_PY_COUNT changed .py file(s) (range=${DIFF_RANGE:-<none>})"

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
    echo_info "[1/4] $SCITEX_DEV_CMD ecosystem audit-all $PKG_NAME --path $REPO_ROOT --severity error"
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
    echo_error "[1/4] scitex-dev not importable. Editable install may have drifted (worktree removed)."
    echo_error "Fix: cd <repo> && uv pip install -e <scitex-dev-checkout>"
    echo_error "     (probed: \`scitex-dev\`, \`python3 -m scitex_dev\`, \`python -m scitex_dev\` — all failed)"
    AUDIT_RC=127
fi

# ----------------------------------------------------------------- #
# Step 2: ruff check --select F401,F811 on CHANGED .py files        #
# ----------------------------------------------------------------- #
#
# F401 (unused import) + F811 (redefined-while-unused) are the two ruff
# rules that bite local→CI churn most often. Both are line-stable and
# fast (microseconds per file). Diff-scoped to keep the gate sub-second
# even on large repos.
#
# --extend-per-file-ignores: package `__init__.py` files canonically
# re-export symbols and would otherwise drown the gate in F401 noise.
#
# Why ONLY F401+F811 (not full ruff): broader linting (E/W/B/UP) is the
# operator's prerogative on their schedule, not the gate's. Picking just
# the two highest-bang-for-buck rules keeps the gate non-controversial:
# you cannot argue with "you imported something and never used it".
RUFF_RC=0
if [[ "$CHANGED_PY_COUNT" -eq 0 ]]; then
    echo_info "[2/4] ruff F401,F811 — no changed .py files, SKIPPED"
elif command -v ruff >/dev/null 2>&1; then
    echo_info "[2/4] ruff check --select F401,F811 ($CHANGED_PY_COUNT file(s))"
    # Feed the file list via xargs so the command line stays bounded;
    # ruff handles large fileset just fine but argv has a hard limit.
    # `--no-cache` keeps the gate stateless — caching would invalidate
    # on every $RUFF_CACHE_DIR-mtime change, which is hostile in CI.
    # We DO want a cache locally, but the small fileset means the
    # cache rarely helps; explicit > implicit.
    echo "$CHANGED_PY" | (
        cd "$REPO_ROOT" && timeout "$DEADLINE_SECONDS" \
            xargs ruff check --select F401,F811 \
                --extend-per-file-ignores '**/__init__.py:F401' >&2
    )
    RUFF_RC=$?
    if [[ "$RUFF_RC" -ne 0 ]]; then
        echo_error "ruff F401/F811 failed (rc=$RUFF_RC)"
    else
        echo_success "ruff F401/F811 clean"
    fi
else
    echo_warning "[2/4] ruff not on PATH — step SKIPPED"
    echo_warning "      install: pip install ruff"
fi

# ----------------------------------------------------------------- #
# Step 3: import-smoke on CHANGED src/ modules                      #
# ----------------------------------------------------------------- #
#
# Catches the "wheel installs but `import scitex_<pkg>.<mod>` raises at
# runtime" class — a syntax error, a top-level NameError, an unguarded
# optional dep, etc. Diff-scoped to the CHANGED src/ files only so the
# gate stays sub-second.
#
# We compute the import dotted-name from the file path by:
#   src/<pkg>/foo/bar.py        → <pkg>.foo.bar
#   src/<pkg>/foo/__init__.py   → <pkg>.foo
# Tests / examples / scripts are intentionally excluded — they are not
# part of the package's public import surface.
IMPORT_SMOKE_RC=0
if [[ "$CHANGED_PY_COUNT" -eq 0 ]]; then
    echo_info "[3/4] import-smoke — no changed .py files, SKIPPED"
else
    # Collect the dotted module names. Empty if no src/ files changed.
    IMPORT_TARGETS="$(
        echo "$CHANGED_PY" | python3 -c "
import sys
for line in sys.stdin.read().splitlines():
    line = line.strip()
    if not line or not line.startswith('src/'):
        continue
    parts = line[len('src/'):].split('/')
    if not parts:
        continue
    # drop trailing .py / __init__.py
    if parts[-1] == '__init__.py':
        parts = parts[:-1]
    elif parts[-1].endswith('.py'):
        parts[-1] = parts[-1][:-3]
    else:
        continue
    if not parts:
        continue
    print('.'.join(parts))
" 2>/dev/null)"
    if [[ -z "$IMPORT_TARGETS" ]]; then
        echo_info "[3/4] import-smoke — no src/ modules in diff, SKIPPED"
    else
        N_TARGETS=$(echo "$IMPORT_TARGETS" | wc -l | tr -d ' ')
        echo_info "[3/4] import-smoke ($N_TARGETS module(s))"
        # We import via the active python (same interpreter used to
        # resolve scitex-dev). The `python3` probe is cheap; failure here
        # means the package can't be imported at all, which is a real
        # bug — block the push.
        ( cd "$REPO_ROOT" && timeout "$DEADLINE_SECONDS" python3 -c "
import importlib, sys
modules = [m for m in '''$IMPORT_TARGETS'''.strip().splitlines() if m]
failed = []
for m in modules:
    try:
        importlib.import_module(m)
    except Exception as e:
        failed.append((m, type(e).__name__, str(e)))
if failed:
    for m, etype, msg in failed:
        print(f'IMPORT FAIL: {m}: {etype}: {msg}', file=sys.stderr)
    sys.exit(1)
" >&2 )
        IMPORT_SMOKE_RC=$?
        if [[ "$IMPORT_SMOKE_RC" -ne 0 ]]; then
            echo_error "import-smoke failed (rc=$IMPORT_SMOKE_RC)"
        else
            echo_success "import-smoke clean"
        fi
    fi
fi

# ----------------------------------------------------------------- #
# Step 4: run_testmon warm-cache wrapper (pytest --testmon)          #
# ----------------------------------------------------------------- #
#
# --testmon picks only the tests whose imported sources have changed
# since the last green run (kept in `.testmondata` at the repo root).
# `-m "not slow and not integration"` excludes heavy markers used
# across the ecosystem. `-x` stops at the first failure so the operator
# sees the failure quickly. The overall `timeout` is the safety net.
#
# We route through the canonical `run_testmon.sh` warm-cache wrapper
# (resolved via `scitex-dev hooks show-path run_testmon`) rather than a
# bare `pytest --testmon`: the wrapper seed-copies a persistent per-(repo,
# pyXY) `.testmondata` into the worktree BEFORE pytest and writes it back
# AFTER, so a FRESH release worktree runs only impacted tests instead of
# cold-running the whole ~2500-test suite. The wrapper also pins an
# absolute interpreter, so this step no longer resolves pytest off the
# ambient $PATH.
TEST_RC=0
if [[ -d "$REPO_ROOT/tests" ]]; then
    # Resolve the wrapper's absolute path through the scitex-dev CLI
    # already located in Step 1. `hooks show-path` prints the bundled
    # run_testmon.sh path; a fallback import keeps the step working if a
    # future refactor changes the CLI surface.
    RUN_TESTMON=""
    if [[ -n "$SCITEX_DEV_CMD" ]]; then
        RUN_TESTMON="$($SCITEX_DEV_CMD hooks show-path run_testmon 2>/dev/null || true)"
    fi
    if [[ -z "$RUN_TESTMON" ]] && command -v python3 >/dev/null 2>&1; then
        RUN_TESTMON="$(python3 -c 'from scitex_dev._hooks import run_testmon_sh_path; print(run_testmon_sh_path())' 2>/dev/null || true)"
    fi
    if [[ -n "$RUN_TESTMON" && -f "$RUN_TESTMON" ]]; then
        echo_info "[4/4] run_testmon (warm-cache) --testmon -x -m 'not slow and not integration'"
        # We deliberately do NOT pass --no-header / -q: the operator
        # needs to see what ran when something fails. stderr is the
        # right channel because git pre-push hooks emit hook output
        # interleaved with the push command's own stderr.
        # Same `if ! cmd` trap as the audit step — capture `$?`
        # directly so the failure message names the real testmon rc,
        # not the inverted truthy 0. The wrapper adds `--testmon`; we
        # forward the selection/flags it should apply.
        ( cd "$REPO_ROOT" && timeout "$DEADLINE_SECONDS" bash "$RUN_TESTMON" \
                -x --tb=short \
                -m "not slow and not integration" \
                tests >&2 )
        TEST_RC=$?
        if [[ "$TEST_RC" -ne 0 ]]; then
            echo_error "scope tests failed (rc=$TEST_RC)"
        else
            echo_success "scope tests clean"
        fi
    else
        echo_warning "[4/4] run_testmon wrapper not resolvable — scope test step SKIPPED"
        echo_warning "      (scitex-dev hooks show-path run_testmon failed; is scitex-dev installed?)"
    fi
else
    echo_warning "[4/4] no tests/ directory — scope test step SKIPPED"
fi

# ----------------------------------------------------------------- #
# Verdict                                                           #
# ----------------------------------------------------------------- #

if [[ "$AUDIT_RC" -ne 0 || "$RUFF_RC" -ne 0 || "$IMPORT_SMOKE_RC" -ne 0 || "$TEST_RC" -ne 0 ]]; then
    echo_error "----------------------------------------------------------"
    echo_error "PUSH BLOCKED by scitex-dev pre-push gate"
    [[ "$AUDIT_RC" -ne 0 ]] && echo_error "  - audit-all returned $AUDIT_RC"
    [[ "$RUFF_RC"  -ne 0 ]] && echo_error "  - ruff F401/F811 returned $RUFF_RC"
    [[ "$IMPORT_SMOKE_RC" -ne 0 ]] && echo_error "  - import-smoke returned $IMPORT_SMOKE_RC"
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
