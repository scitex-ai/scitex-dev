#!/bin/bash
# commit-msg hook: reject Claude Co-Authored-By trailer in scitex repos.
#
# Per scitex CLA policy (memory: feedback_no_claude_coauthor_trailer.md),
# the Co-Authored-By Claude trailer trips CLA Assistant. The allowlist
# approach is unsafe (would admit any claude-prefixed GitHub user), so
# the trailer is dropped entirely.
#
# This hook lives at .git/hooks/commit-msg in each scitex-* repo,
# installed by scripts/install-commit-hooks.sh.

set -eu

MSG_FILE="$1"

if grep -qE 'Co-Authored-By:.*[Cc]laude|<noreply@anthropic\.com>' "$MSG_FILE"; then
    cat >&2 <<'EOM'

ERROR: Commit message contains a Claude Co-Authored-By trailer.

Per scitex CLA policy, the trailer must NOT be added to commits in this
project. The CLA Assistant treats the trailer as an unsigned contributor.

Fix: remove any line matching:
  Co-Authored-By: Claude <...>
  Co-Authored-By: ... <noreply@anthropic.com>

Then retry the commit.
EOM
    exit 1
fi

exit 0
