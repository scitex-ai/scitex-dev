#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# scitex-dev canonical git pre-commit hook: LOCAL `main` IS A MIRROR.
#
# Operator ruling, 2026-08-30. There is exactly one road into `main`, and
# a local commit is not on it:
#
#     local develop -> topic branch -> push -> PR to origin/develop
#       -> pull to local develop -> tag, push to origin/develop
#       -> origin/main; publish -> pull to local main
#
# So the only legitimate operation on local `main` is `pull`. Everything
# else reaches it by having gone through develop and a release.
#
# WHY THIS EXISTS RATHER THAN A CONVENTION. Measured the night this was
# written: `main` was ahead of `develop` in every repository checked,
# because real feature PRs had been merged with `main` as the base. A
# fleet-wide licence fix landed on three repositories' main and none of
# their develops, and three release PRs had been CONFLICTED for weeks as
# a direct result.
#
# WHAT THIS DOES NOT TOUCH — the release path. A release TAGS and PUSHES;
# it never commits, and the merge of develop into main happens on the
# REMOTE through a pull request. `scitex_dev._release.publisher` contains
# no `git commit` at all and already runs its pushes under
# `-c core.hooksPath=/dev/null`. A pre-commit hook cannot fire on any of
# that.
#
# Escape hatches, both deliberately loud:
#     SCITEX_DEV_ALLOW_MAIN_COMMIT=1 git commit ...
#     git commit --no-verify ...

set -euo pipefail

BRANCH="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"

# Detached HEAD (a rebase, a bisect, a checked-out tag) has no branch to
# protect. Say nothing and get out of the way.
if [[ -z "$BRANCH" ]]; then
    exit 0
fi

case "$BRANCH" in
main | master) ;;
*) exit 0 ;;
esac

if [[ -n "${SCITEX_DEV_ALLOW_MAIN_COMMIT:-}" ]]; then
    echo "scitex-dev: SCITEX_DEV_ALLOW_MAIN_COMMIT=1 — allowing a commit on '$BRANCH'." >&2
    exit 0
fi

cat >&2 <<EOF

  REFUSED: commit on '$BRANCH'.

  Local '$BRANCH' is a READ-ONLY MIRROR of origin/$BRANCH. Its only
  legitimate operation is 'pull'. Every change reaches it by having gone
  through develop and a release:

    1. start on local develop
    2. cut a topic branch
    3. push the topic branch
    4. open a PR into origin/develop
    5. pull the merge back to local develop
    6. tag, push to origin/develop, then origin/main; publish
    7. pull to local main

  You are at step 1 or 2. Move this work onto a topic branch:

    git branch <topic>            # keep what you staged
    git checkout <topic>
    git commit ...

  If you are on '$BRANCH' with nothing staged yet, just:

    git checkout develop

  Escape hatches, if you genuinely mean it:
    SCITEX_DEV_ALLOW_MAIN_COMMIT=1 git commit ...
    git commit --no-verify ...

EOF
exit 1

# EOF
