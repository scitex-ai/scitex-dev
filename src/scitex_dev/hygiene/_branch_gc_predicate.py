#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""THE SAFETY PREDICATE — the whole point of the branch GC.

A branch is deletable **iff ALL FIVE** legs pass:

1. **LANDED** — the work exists on a base, proven by ANY of three sources
   (ancestor / patch-equivalence / merged PR).
2. **OLD** — older than the (clamped) age floor, by the CONSERVATIVE of two
   age signals.
3. **UNCHECKED-OUT** — not the HEAD of the main checkout or any linked
   worktree.
4. **UNPROTECTED** — not a protected name, and no open PR.
5. **NOT ACTIVE SUBSTRATE** — no non-terminal card names it.

Every leg returns ``True`` / ``False`` / ``None``, and ``None`` ("could not
look") is treated exactly like ``False`` ("looked, it failed"): both KEEP.
A boolean leg would have to fold "I could not tell" into one pole or the
other, and whichever pole it picked would eventually be wrong in the
direction that destroys work.

``git branch --merged`` IS NEVER CALLED, ANYWHERE
-------------------------------------------------
It is the ANCESTOR check wearing a friendlier name, and ancestry is blind
to squash-merges: a squash commit is a NEW commit, so a squash-merged
branch is not an ancestor of its base and ``--merged`` calls it unmerged
forever. Measured on ``scitex-agent-container`` while designing this: 55
local branches, 5 reported by the ancestor check — 9% coverage, in a repo
that squash-merges. A predicate with that recall is not a safety feature,
it is a tool that does nothing while appearing to work. A source-level
test asserts the string does not appear in this package.
"""

from __future__ import annotations

from pathlib import Path

from ._branch_gc_active import branch_is_active
from ._branch_gc_model import (
    KEEP_ACTIVE_WORK,
    KEEP_ACTIVE_WORK_UNKNOWN,
    KEEP_AGE_UNKNOWN,
    KEEP_CHECKED_OUT,
    KEEP_LANDED_UNKNOWN,
    KEEP_NOT_LANDED,
    KEEP_OPEN_PR,
    KEEP_PR_STATE_UNKNOWN,
    KEEP_PROTECTED,
    KEEP_TOO_YOUNG,
    LANDED_BY_ANCESTOR,
    LANDED_BY_MERGED_PR,
    LANDED_BY_PATCH_EQUIVALENCE,
    MERGE_BASES,
    BranchInfo,
    BranchVerdict,
    Landed,
    is_protected_name,
)
from ._branch_gc_probe import (
    PrLookup,
    commit_epoch,
    is_ancestor_of_base,
    patch_equivalent_to_base,
    reflog_epoch,
)

__all__ = [
    "SECONDS_PER_DAY",
    "is_landed",
    "is_not_active",
    "is_old_enough",
    "is_unchecked_out",
    "is_unprotected",
    "verdict_for",
]

SECONDS_PER_DAY = 86400.0


def is_landed(
    repo: str | Path,
    branch: str,
    pr_merged: PrLookup,
    bases: tuple[str, ...] = MERGE_BASES,
) -> Landed:
    """Leg 1 — did this work land? THREE sources, asymmetrically combined.

    Order is deliberate. The two LOCAL sources run first because they are
    free and cannot lie; only when neither can see the work do we ask
    GitHub, because "landed but invisible locally" is exactly the shape a
    multi-commit squash leaves behind.

    A definite NOT-LANDED requires ALL THREE to agree, and requires that we
    actually READ a base to say so: not an ancestor of a base we read, not
    patch-equivalent on a base we read, AND GitHub answering "no merged
    PR". One source alone is not corroboration — a bare "gh says no" with
    no readable base is an UNKNOWN, and an UNKNOWN keeps.
    """
    evaluated = False
    for base in bases:
        ancestor, base_read = is_ancestor_of_base(repo, branch, base)
        evaluated = evaluated or base_read
        if ancestor is True:
            return Landed(value=True, source=LANDED_BY_ANCESTOR)
    for base in bases:
        equivalent, base_read = patch_equivalent_to_base(repo, branch, base)
        evaluated = evaluated or base_read
        if equivalent is True:
            return Landed(value=True, source=LANDED_BY_PATCH_EQUIVALENCE)
    try:
        pr = pr_merged(Path(str(repo)), branch)
    except Exception:  # noqa: BLE001 - an injected seam raising is UNKNOWN
        pr = None
    if pr is True:
        return Landed(value=True, source=LANDED_BY_MERGED_PR)
    if pr is False and evaluated:
        return Landed(value=False, reason=KEEP_NOT_LANDED)
    return Landed(value=None, reason=KEEP_LANDED_UNKNOWN)


def is_old_enough(
    repo: str | Path, branch: str, min_age_days: float, now: float
) -> tuple[bool | None, str]:
    """Leg 2 — THE AGE FLOOR. The property whose absence destroyed 7 branches.

    Age is the MINIMUM of the signals we can read — the conservative
    direction. A branch whose tip commit is a year old but whose ref was
    created in this clone an hour ago is YOUNG, because the thing that
    matters is whether someone is working on it now, not when the code it
    points at was written. That is the exact shape the incident had.

    Both signals unreadable -> ``None`` -> KEEP.
    """
    signals = [
        value
        for value in (commit_epoch(repo, branch), reflog_epoch(repo, branch))
        if value is not None
    ]
    if not signals:
        return None, KEEP_AGE_UNKNOWN
    newest = max(signals)  # newest timestamp == youngest age
    age_days = (now - newest) / SECONDS_PER_DAY
    return (True, "") if age_days >= min_age_days else (False, KEEP_TOO_YOUNG)


def is_unchecked_out(branch: str, heads: set[str] | None) -> tuple[bool | None, str]:
    """Leg 3 — not the HEAD of the main checkout or of any linked worktree.

    ``git branch -d`` enforces this too; this leg exists so the REASON is
    legible in the report rather than surfacing as a bare "skipped".
    ``heads is None`` means the worktree listing was unreadable — UNKNOWN,
    never an empty set.
    """
    if heads is None:
        return None, KEEP_CHECKED_OUT
    return (False, KEEP_CHECKED_OUT) if branch in heads else (True, "")


def is_unprotected(
    repo: str | Path,
    branch: str,
    pr_open: PrLookup,
    extra_globs: tuple[str, ...] = (),
) -> tuple[bool | None, str]:
    """Leg 4 — not a protected name, and no open PR (or unknown PR state).

    The name check is not configurable downward: ``extra_globs`` only ever
    ADDS. The open-PR check returns KEEP on any doubt, matching the
    behaviour ``_prune_merged._has_open_pr`` already chose.
    """
    if is_protected_name(branch, extra_globs):
        return False, KEEP_PROTECTED
    try:
        opened = pr_open(Path(str(repo)), branch)
    except Exception:  # noqa: BLE001 - an injected seam raising is UNKNOWN
        opened = None
    if opened is True:
        return False, KEEP_OPEN_PR
    if opened is None:
        return None, KEEP_PR_STATE_UNKNOWN
    return True, ""


def is_not_active(branch: str, tokens: set[str] | None) -> tuple[bool | None, str]:
    """Leg 5 — no non-terminal card names this branch.

    ``tokens is None`` is UNAVAILABLE, and the engine turns that into a
    whole-pass ABORT rather than a per-branch keep — see
    :mod:`._branch_gc_active`. This function still reports it as a keep
    reason so a caller that ignores the abort cannot silently delete.
    """
    if tokens is None:
        return None, KEEP_ACTIVE_WORK_UNKNOWN
    return (False, KEEP_ACTIVE_WORK) if branch_is_active(branch, tokens) else (True, "")


def verdict_for(
    repo: str | Path,
    info: BranchInfo,
    *,
    min_age_days: float,
    now: float,
    pr_merged: PrLookup,
    pr_open: PrLookup,
    heads: set[str] | None,
    active_tokens: set[str] | None,
    extra_globs: tuple[str, ...] = (),
) -> BranchVerdict:
    """Run all five legs and collect EVERY keep reason, not just the first.

    No leg short-circuits. "31 kept" tells an operator nothing; "22
    not-landed, 6 too-young, 3 active-work" tells them what to do — and,
    more importantly, lets them audit a pass after it ran.

    (``is_unprotected`` checks the NAME before it asks GitHub anything, so
    a protected branch still costs no network round-trip — but its answer
    is one of five collected reasons, not an early return.)
    """
    landed = is_landed(repo, info.name, pr_merged)
    legs = [
        (landed.value, landed.reason),
        is_old_enough(repo, info.name, min_age_days, now),
        is_unchecked_out(info.name, heads),
        is_unprotected(repo, info.name, pr_open, extra_globs),
        is_not_active(info.name, active_tokens),
    ]
    reasons = [reason for ok, reason in legs if ok is not True and reason]
    return BranchVerdict(
        name=info.name,
        sha=info.sha,
        keep_reasons=tuple(reasons),
        landed_source=landed.source,
    )


# EOF
