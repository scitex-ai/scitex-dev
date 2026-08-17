#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# File: src/scitex_dev/hooks/require_mergeable_verdict.sh
#
# PRE-TOOL-USE HOOK — refuse `gh pr merge` without a machine verdict.
#
# The operator asked for this as a HOOK rather than a prompt, in these words
# (Telegram, 2026-08-09):
#
#     「なんでプログラムにできることをエージェントにお願いしてんの?
#       プロンプトとか弱いよ? hook とかで強制でしょ?」
#
# WHY IT SHIPS FROM THE PACKAGE RATHER THAN BEING COPIED INTO A HOOKS DIR.
# The first version of this file lived as an UNTRACKED file in one container's
# dotfiles checkout. On 2026-08-16 it was found GONE — no git object, no diff,
# no reflog, nothing to recover. Measured the same hour: `scitex-dev ci verify`,
# the checker this hook calls, was still alive and unchanged, because it ships
# inside the distribution. The half that was installed survived a container
# rebuild; the half that was copied did not, and its absence was SILENT — seven
# pull requests merged that night without the gate firing, and nothing said so.
# A missing gate does not error. That is the whole reason this file is here.
#
# It also removes the version-skew hazard: hook and checker are now released
# together, so they cannot disagree about the exit-code vocabulary below.

set -uo pipefail

# THE CONTRACT — src/scitex_dev/ci/_exit_codes.py is the SSoT; these mirror it.
# Do not "simplify" them to 0/1. NOT_READY is 10 and CANNOT_DETERMINE is 11
# precisely because 1 and 2 are framework-reserved: Click exits 2 for an
# unknown subcommand BEFORE any of our code runs, so a domain meaning parked
# there is indistinguishable from a typo or a stale install. On 2026-08-09
# that exact collision made a GREEN pull request report as NOT ready to merge.
readonly EXIT_READY=0
readonly EXIT_NOT_READY=10
readonly EXIT_CANNOT_DETERMINE=11
readonly EXIT_USAGE=2 # NOT ours. Named so we can RECOGNISE it.

_hook_allow() { exit 0; }

_hook_block() {
    # Blocking message goes to stderr; exit 2 is this HOOK's protocol with the
    # harness (deny), and is unrelated to the checker's vocabulary above.
    printf '%s\n' "$1" >&2
    exit 2
}

# Only gate the command we mean. Anything else passes untouched: a gate that
# fires on unrelated commands gets disabled, and a disabled gate is no gate.
_is_pr_merge() {
    local cmd="$1"
    [[ "$cmd" == *"gh"* ]] && [[ "$cmd" == *" pr "* ]] && [[ "$cmd" == *" merge"* ]]
}

main() {
    local payload command
    payload="$(cat)"

    command="$(printf '%s' "$payload" |
        "${SCITEX_DEV_PYTHON:-python3}" -c \
            'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
print((d.get("tool_input") or {}).get("command", ""))' 2>/dev/null)"

    # An UNREADABLE payload is not an absent one. We cannot tell whether this
    # is a merge, so we cannot claim it is safe -- but neither can we block
    # every tool call on a parse failure. Pass, and say so, loudly enough to
    # be found in a transcript.
    if [[ -z "$command" ]]; then
        printf 'require_mergeable_verdict: could not read tool_input.command; NOT gating this call\n' >&2
        _hook_allow
    fi

    _is_pr_merge "$command" || _hook_allow

    if ! command -v scitex-dev >/dev/null 2>&1; then
        _hook_block "BLOCKED: \`scitex-dev\` is not on PATH, so the merge verdict cannot be obtained.
This hook ships WITH scitex-dev; if the command is missing, the install is broken.
Absence of the checker is not permission to merge."
    fi

    local verdict_output rc
    verdict_output="$(scitex-dev ci verify 2>&1)"
    rc=$?

    case "$rc" in
    "$EXIT_READY")
        _hook_allow
        ;;
    "$EXIT_NOT_READY")
        _hook_block "BLOCKED: \`scitex-dev ci verify\` says this PR is NOT ready to merge.

${verdict_output}

Fix the named check, or merge deliberately outside this hook if you have a
reason the checker cannot see -- but do not merge because a badge looked green."
        ;;
    "$EXIT_CANNOT_DETERMINE")
        _hook_block "BLOCKED: \`scitex-dev ci verify\` COULD NOT DETERMINE whether this PR is mergeable.

${verdict_output}

This is not a 'no' -- it is 'I could not tell', and the two call for different
actions. Find out why the question could not be answered; do not read silence
as a yes."
        ;;
    "$EXIT_USAGE")
        _hook_block "BLOCKED: \`scitex-dev ci verify\` exited ${rc} (usage error).

${verdict_output}

Exit 2 is Click's UNKNOWN-SUBCOMMAND code, raised before any of our code runs,
so the likely cause is a STALE OR BROKEN scitex-dev install that lacks the
\`ci verify\` verb -- not a verdict about this PR. On 2026-08-09 this exact
condition made a green PR read as 'NOT ready'. Check \`scitex-dev --version\`
and the venv on PATH."
        ;;
    *)
        _hook_block "BLOCKED: \`scitex-dev ci verify\` exited ${rc}, which is not a verdict this hook recognises.

${verdict_output}

Recognised: ${EXIT_READY}=ready, ${EXIT_NOT_READY}=not-ready, ${EXIT_CANNOT_DETERMINE}=cannot-determine, ${EXIT_USAGE}=usage.
An unrecognised code is failing CLOSED on purpose: an exit code nobody planned
for is exactly how 'I could not tell' becomes 'yes'."
        ;;
    esac
}

main "$@"

# EOF
