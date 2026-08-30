#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The decision function. Reads nothing, writes nothing, deletes nothing.

Pure on purpose: a sweep whose reasoning lives inside the code that
deletes can only be reviewed by running it, and running it is the part
that deletes. Everything here takes :class:`~._model.BranchFacts` and
returns a verdict.

THE ORDER OF THE CHECKS IS THE DESIGN
-------------------------------------
1. protected name        — exact match, at any age
2. open-PR state UNKNOWN — nobody answered; refuse to judge
3. open PR               — work someone OWES, not work abandoned
4. merged into develop   — finished, HOWEVER RECENTLY TOUCHED
5. age unknown           — refuse to judge
6. touched inside window — still in flight
7. otherwise             — stale, drop

Two of those positions were each bought with a near-miss.

**(2) above (4).** A half-answer from GitHub that happens to carry
``merged`` while the open-PR lookup failed would otherwise license a
drop on the strength of the half that arrived. Deleting an open PR's
head closes the PR and destroys the review; there is no cheap recovery.

**(4) above (6).** "Untouched for 24h" ALONE keeps every branch whose PR
merged today, because merging touches the branch. Measured, that left a
keep set of 16 branches across 6 repositories; with the merged rule
ahead of the age rule it left 1.
"""

from __future__ import annotations

from ._model import (
    DEFAULT_MAX_AGE_HOURS,
    DROP_MERGED,
    DROP_STALE,
    KEEP_AGE_UNKNOWN,
    KEEP_AMBIGUOUS_NAME,
    KEEP_CURRENT_HEAD,
    KEEP_OPEN_PR,
    KEEP_PR_UNKNOWN,
    KEEP_PROTECTED,
    KEEP_RECENT,
    KEEP_WORKTREE_BUSY,
    KEEP_WORKTREE_UNKNOWN,
    PROTECTED_EXACT,
    WT_KEEP,
    WT_NONE,
    WT_REMOVE,
    WT_REMOVE_FORCE,
    AMBIGUOUS_REMOTE_NAMES,
    BranchFacts,
    BranchVerdict,
)

SECONDS_PER_HOUR = 3600.0


def age_hours(epoch: float | None, *, now: float) -> float | None:
    """How long ago ``epoch`` was, in hours, or ``None`` if unmeasured.

    Clamped at zero: a clock skew that puts a stamp in the future must
    read as "just now", never as a negative age that sorts as ancient.
    """
    if epoch is None:
        return None
    return max(0.0, (now - epoch) / SECONDS_PER_HOUR)


def is_protected(name: str, *, protected: frozenset[str] = PROTECTED_EXACT) -> bool:
    """EXACT membership. Never a prefix, never a glob.

    See :mod:`._model` for the two measured failures that make this an
    exact-match test — ``^cla$`` missed the signature store, and ``cla*``
    swallowed ``claude/*``.
    """
    return name in protected


def classify(
    facts: BranchFacts,
    *,
    now: float,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    protected: frozenset[str] = PROTECTED_EXACT,
) -> BranchVerdict:
    """Keep or drop ``facts``, ignoring any worktree that holds it.

    The worktree question is a SECOND question — "this branch is
    finished, what stands in the way of removing it?" — and it is
    answered by :func:`worktree_plan` so that a branch's fate and a
    working tree's fate never get decided in one tangled expression.
    """
    if is_protected(facts.name, protected=protected):
        return BranchVerdict(
            name=facts.name, sha=facts.sha, drop=False, reason=KEEP_PROTECTED
        )
    if facts.has_open_pr is None:
        return BranchVerdict(
            name=facts.name, sha=facts.sha, drop=False, reason=KEEP_PR_UNKNOWN
        )
    if facts.has_open_pr:
        return BranchVerdict(
            name=facts.name, sha=facts.sha, drop=False, reason=KEEP_OPEN_PR
        )
    if facts.merged:
        return BranchVerdict(
            name=facts.name, sha=facts.sha, drop=True, reason=DROP_MERGED
        )
    hours = age_hours(facts.touched_epoch, now=now)
    if hours is None:
        return BranchVerdict(
            name=facts.name, sha=facts.sha, drop=False, reason=KEEP_AGE_UNKNOWN
        )
    if hours < max_age_hours:
        return BranchVerdict(
            name=facts.name, sha=facts.sha, drop=False, reason=KEEP_RECENT
        )
    return BranchVerdict(name=facts.name, sha=facts.sha, drop=True, reason=DROP_STALE)


def worktree_plan(
    facts: BranchFacts,
    *,
    now: float,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> tuple[str, str]:
    """``(action, keep_reason)`` for a branch already judged droppable.

    A worktree holding a finished branch is itself finished — treating
    git's "checked out in a worktree" refusal as a terminus was the
    original mistake, and on one host it accounted for 59 of 68 reported
    failures. So the refusal is a signal to take one more step, not a
    stopping point.

    THE INSTRUMENT CHANGES WITH THE QUESTION. For a CLEAN worktree the
    branch date answers "is anyone working here?" perfectly well. For a
    worktree carrying UNCOMMITTED work it answers nothing at all: the
    edits are not in any commit, so a tree whose files were touched an
    hour ago can carry a three-week-old tip. Forcing on that reading
    destroys an hour-old edit. Uncommitted work is therefore measured on
    the FILES.
    """
    if facts.worktree_path is None:
        return WT_NONE, ""
    if facts.worktree_is_primary:
        return WT_KEEP, KEEP_CURRENT_HEAD
    if facts.worktree_dirty is None:
        return WT_KEEP, KEEP_WORKTREE_UNKNOWN
    if not facts.worktree_dirty:
        return WT_REMOVE, ""
    hours = age_hours(facts.worktree_touch_epoch, now=now)
    if hours is None:
        return WT_KEEP, KEEP_WORKTREE_UNKNOWN
    if hours < max_age_hours:
        return WT_KEEP, KEEP_WORKTREE_BUSY
    return WT_REMOVE_FORCE, ""


def decide(
    facts: BranchFacts,
    *,
    now: float,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    protected: frozenset[str] = PROTECTED_EXACT,
) -> BranchVerdict:
    """The whole local judgement: branch fate, then worktree fate."""
    verdict = classify(
        facts, now=now, max_age_hours=max_age_hours, protected=protected
    )
    if not verdict.drop:
        return verdict
    action, keep_reason = worktree_plan(facts, now=now, max_age_hours=max_age_hours)
    if keep_reason:
        return BranchVerdict(
            name=verdict.name,
            sha=verdict.sha,
            drop=False,
            reason=keep_reason,
            worktree_path=facts.worktree_path,
            worktree_action=WT_KEEP,
        )
    return BranchVerdict(
        name=verdict.name,
        sha=verdict.sha,
        drop=True,
        reason=verdict.reason,
        worktree_path=facts.worktree_path,
        worktree_action=action,
    )


def decide_remote(
    facts: BranchFacts,
    *,
    now: float,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    protected: frozenset[str] = PROTECTED_EXACT,
) -> BranchVerdict:
    """The remote judgement. No worktree axis; one extra refusal.

    ``git push origin --delete origin`` cannot say whether ``origin``
    names the remote or the ref, and fails. That is a benign, permanent
    property of the NAME — retrying cannot help and forcing must not be
    attempted — so it is reported as a keep with its own reason.
    """
    verdict = classify(
        facts, now=now, max_age_hours=max_age_hours, protected=protected
    )
    if verdict.drop and facts.name in AMBIGUOUS_REMOTE_NAMES:
        return BranchVerdict(
            name=verdict.name,
            sha=verdict.sha,
            drop=False,
            reason=KEEP_AMBIGUOUS_NAME,
        )
    return verdict


# EOF
