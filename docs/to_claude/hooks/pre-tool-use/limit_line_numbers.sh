#!/bin/bash
# -*- coding: utf-8 -*-
# Timestamp: "2026-04-10 09:13:10 (ywatanabe)"
# File: ./src/.claude/to_claude/hooks/pre-tool-use/limit_line_numbers.sh

GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"

GRAY='\033[0;90m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo_info() { echo -e "${GRAY}INFO: $1${NC}"; }
echo_success() { echo -e "${GREEN}SUCC: $1${NC}"; }
echo_warning() { echo -e "${YELLOW}WARN: $1${NC}"; }
echo_error() { echo -e "${RED}ERRO: $1${NC}"; }
echo_header() { echo_info "=== $1 ==="; }
# ---------------------------------------

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_PATH="$THIS_DIR/.$(basename "$0").log"
echo >"$LOG_PATH" 2>/dev/null || true

# Description: Claude Code hook to enforce file size limits

# --self-test: verify hook works with sample input
if [[ "${1:-}" == "--self-test" ]]; then
    echo "=== Self-test: $(basename "$0") ==="
    pass=0
    fail=0

    # Test 1: small file should pass (exit 0)
    # shellcheck disable=SC2034
    result=$(printf '%s' '{"tool_name":"Write","tool_input":{"file_path":"/tmp/test_hook.py","content":"print(1)\nprint(2)\n"},"cwd":"/tmp","session_id":"test","tool_use_id":"test-1"}' | "$0" 2>&1) && rc=$? || rc=$?
    if [[ $rc -eq 0 ]]; then
        ((pass++))
        echo "  PASS: small file allowed (exit $rc)"
    else
        ((fail++))
        echo "  FAIL: small file should pass (exit $rc)"
    fi

    echo "Results: $pass passed, $fail failed"
    [[ $fail -eq 0 ]] && exit 0 || exit 1
fi

set -euo pipefail

# Check if hook is enabled via centralized project-switch/switch.yaml
HELPER_SCRIPT="$(dirname "$THIS_DIR")/project-switch/hook_switch_helper.sh"
if [[ -f "$HELPER_SCRIPT" ]]; then
    # shellcheck source=/dev/null
    source "$HELPER_SCRIPT"
    check_hook_enabled_or_exit "$(basename "$0")"
fi

# Read input early for bypass check
INPUT="$(cat)"

# Allow bypass with comment in content: hook-bypass: line-limit
if echo "$INPUT" | grep -qF 'hook-bypass: line-limit'; then
    exit 0
fi

# Thresholds (in lines)
THRESHOLD_TS=512
THRESHOLD_PY=512
THRESHOLD_CSS=512
THRESHOLD_HTML=1024
THRESHOLD_MARKDOWN=512
REFACTORING_MD="$GIT_ROOT/GITIGNORED/REFACTORING.md"

# Parse JSON using Python - outputs tab-separated values with line counts
# Capture output and exit code separately to properly handle parse failures
PARSED_OUTPUT=""
if ! PARSED_OUTPUT=$(echo "$INPUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
ti = d.get("tool_input", {}) or {}

def get_val(k):
    return (ti.get(k) or "").replace("\r\n", "\n")

file_path = get_val("file_path")
content = get_val("content")
old_string = get_val("old_string")
new_string = get_val("new_string")

# Count lines (add 1 if non-empty and no trailing newline for accurate count)
def count_lines(s):
    if not s:
        return 0
    return s.count("\n") + (1 if not s.endswith("\n") else 0)

content_lines = count_lines(content) if content else -1
old_lines = count_lines(old_string) if old_string else -1
new_lines = count_lines(new_string) if new_string else -1

print(f"{file_path}\t{content_lines}\t{old_lines}\t{new_lines}")
' 2>/dev/null); then
    # Failed to parse JSON - approve silently (non-monitored tool or malformed input)
    exit 0
fi

read -r FILE_PATH CONTENT_LINES OLD_LINES NEW_LINES <<<"$PARSED_OUTPUT"

# Exit if no file path (non-file operation or unsupported tool)
[ -n "$FILE_PATH" ] || exit 0

# Skip test files and CHANGELOG.md
case "$FILE_PATH" in
*/tests/* | */test_*.py | *_test.py | */CHANGELOG.md | CHANGELOG.md) exit 0 ;;
esac

# Determine threshold based on extension
ext="${FILE_PATH##*.}"
case "$ext" in
py | el | sh | src) THRESHOLD="$THRESHOLD_PY" ;;
ts | tsx | js | jsx) THRESHOLD="$THRESHOLD_TS" ;;
css) THRESHOLD="$THRESHOLD_CSS" ;;
html | htm) THRESHOLD="$THRESHOLD_HTML" ;;
md) THRESHOLD="$THRESHOLD_MARKDOWN" ;;
*) exit 0 ;;
esac

# Get current file line count
CURRENT=0
if [ -f "$FILE_PATH" ]; then
    CURRENT="$(wc -l <"$FILE_PATH" | tr -d ' ')"
fi

# Calculate proposed line count
if [ "$CONTENT_LINES" -ge 0 ]; then
    # Write operation: content specifies full file
    PROPOSED="$CONTENT_LINES"
elif [ "$OLD_LINES" -ge 0 ]; then
    # Edit operation: calculate delta
    PROPOSED=$((CURRENT - OLD_LINES + NEW_LINES))
    [ "$PROPOSED" -lt 0 ] && PROPOSED=0
else
    PROPOSED="$CURRENT"
fi

# Allow incremental reduction if currently over limit and edit shrinks it
if [ "$CURRENT" -gt "$THRESHOLD" ] && [ "$PROPOSED" -lt "$CURRENT" ]; then
    exit 0
fi

# Active refactoring — bypass line limit. The companion notice hook
# (notify_refactoring_md.sh) emits the active-refactor banner using
# the SAME file + SAME emptiness rule (any non-blank line counts as
# an active entry). Keep these two checks in sync — they are the
# matched pair operators rely on. Empty / whitespace-only file does
# NOT bypass: a blank REFACTORING.md is treated as "no active
# refactor" so a stale empty file can't keep the limit suspended.
if [ -f "$REFACTORING_MD" ] && [ -s "$REFACTORING_MD" ] &&
    grep -q '[^[:space:]]' "$REFACTORING_MD" 2>/dev/null; then
    exit 0
fi

# Self-clean: if REFACTORING.md exists but is empty / whitespace-only,
# delete it. Keeps GITIGNORED/ tidy — notify_refactoring_md.sh does the
# same on its code path. Safe because scan_oversized --apply recreates
# it on demand.
if [ -f "$REFACTORING_MD" ] && { [ ! -s "$REFACTORING_MD" ] ||
    ! grep -q '[^[:space:]]' "$REFACTORING_MD" 2>/dev/null; }; then
    rm -f "$REFACTORING_MD" 2>/dev/null || true
fi

# Block any change that leaves file above threshold
if [ "$PROPOSED" -gt "$THRESHOLD" ]; then
    {
        echo "File size violation: $FILE_PATH"
        echo "  Lines: $PROPOSED (max: $THRESHOLD for .$ext)"
        echo ""
        echo "Rules:"
        echo "  - PY/SH/EL: max $THRESHOLD_PY lines"
        echo "  - TS/JS:    max $THRESHOLD_TS lines"
        echo "  - CSS:      max $THRESHOLD_CSS lines"
        echo "  - HTML:     max $THRESHOLD_HTML lines"
        echo "  - MD:       max $THRESHOLD_MARKDOWN lines"
        echo ""
        echo "Refactoring required (do this BEFORE the blocked edit):"
        echo ""
        echo "  Step 0. PAUSE the current task. This refactor takes priority."
        echo "          Do not attempt to bypass by squeezing/deleting lines."
        echo ""
        echo "  Step 1. Create $REFACTORING_MD and write:"
        echo "            - the file you're refactoring"
        echo "            - the split plan (which logical groups → which new files/dirs)"
        echo "          While this file exists with non-blank content, the line"
        echo "          limit is suspended so you can land the refactor."
        echo ""
        echo "  Step 2. Split the oversized file into focused modules:"
        echo "            - one cohesive responsibility per file"
        echo "            - leave the original as a thin orchestrator that"
        echo "              re-exports the public API (preserves imports)"
        echo "            - group related new files under a subdirectory when"
        echo "              ≥3 files share a common prefix or theme"
        echo "            - follow the project's existing naming conventions"
        echo "            - do not delete code or hide it behind workarounds;"
        echo "              line shrink must come from genuine extraction"
        echo "          Note: linters/formatters may add lines on save —"
        echo "          aim well below the threshold, not exactly at it."
        echo ""
        echo "  Step 2.5. Check the surrounding directory while you're here."
        echo "            If sibling files show the same smell that produced"
        echo "            this oversized file (flat clusters of files sharing"
        echo "            a common prefix, parallel modules with duplicated"
        echo "            scaffolding, etc.), refactor them in the same pass."
        echo "            One coherent reorganization is better than fixing"
        echo "            the same shape five times across five separate PRs."
        echo ""
        echo "  Step 3. Verify (tests pass, imports still resolve), then"
        echo "          delete $REFACTORING_MD to re-arm the limit."
    } >&2
    exit 2
fi

exit 0

# EOF
