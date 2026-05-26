#!/bin/bash
# Install commit-msg hook that rejects Claude Co-Authored-By trailer across
# all scitex-* / scitex-lead / scitex-agent-container / scitex-python clones
# under /home/ywatanabe/proj/.
#
# Why: scitex repos use CLA Assistant. The Co-Authored-By Claude trailer trips
# CLA as an unsigned contributor. Operator decision (2026-05-19): drop the
# trailer entirely rather than allowlist Claude-prefixed GH users (which would
# unsafely admit any Anthropic Claude consumer).
#
# This script is idempotent — re-running just overwrites the hook.
# Run on each fresh clone or when adding a new scitex-* repo locally.

set -eu

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK_SRC="$SCRIPT_DIR/_commit-msg-no-claude-trailer.sh"

if [ ! -f "$HOOK_SRC" ]; then
    echo "ERROR: hook source not found at $HOOK_SRC" >&2
    exit 1
fi

INSTALLED=0
SKIPPED=0

install_to() {
    local d="$1"
    local hookdir
    if [ -d "$d/.git" ]; then
        hookdir="$d/.git/hooks"
    elif [ -f "$d/.git" ]; then
        # Worktree case
        local gitdir
        gitdir=$(awk '/^gitdir:/{print $2}' "$d/.git")
        hookdir="$gitdir/hooks"
    else
        SKIPPED=$((SKIPPED + 1))
        return
    fi

    cp -f "$HOOK_SRC" "$hookdir/commit-msg"
    chmod +x "$hookdir/commit-msg"
    INSTALLED=$((INSTALLED + 1))
}

# Standard scitex-* layout
for d in /home/ywatanabe/proj/scitex-*; do
    install_to "$d"
done

# Plus the non-glob siblings
for d in /home/ywatanabe/proj/scitex-lead \
    /home/ywatanabe/proj/scitex-agent-container \
    /home/ywatanabe/proj/scitex-python; do
    install_to "$d"
done

echo "Installed commit-msg hook in $INSTALLED repos (skipped $SKIPPED non-git dirs)."
