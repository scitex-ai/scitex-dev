#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The decision function, pinned at every boundary that cost something.

The two tests that matter most are
``test_cla_signatures_is_protected_by_exact_name`` (the rehearsal that
would have erased 36 repositories' contributor signatures) and
``test_dirty_worktree_touched_recently_keeps_both`` (the one branch of
the logic whose failure destroys work that exists nowhere else).
"""

from __future__ import annotations

from scitex_dev.branch_hygiene import (
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
    WT_KEEP,
    WT_NONE,
    WT_REMOVE,
    WT_REMOVE_FORCE,
    BranchFacts,
    classify,
    decide,
    decide_remote,
    worktree_plan,
)

NOW = 1_000_000.0
HOUR = 3600.0


def facts(name: str, **kwargs) -> BranchFacts:
    """A branch that would be dropped as stale unless a test says otherwise."""
    base = {
        "sha": "deadbeef",
        "last_commit_epoch": NOW - 100 * HOUR,
        "merged": False,
        "has_open_pr": False,
    }
    base.update(kwargs)
    return BranchFacts(name=name, **base)


# ------------------------------------------------------------------ #
# Protection — exact names, and only exact names.                     #
# ------------------------------------------------------------------ #


def test_cla_signatures_is_protected_by_exact_name():
    """THE REHEARSAL FINDING: `^cla$` did not match this, and 36 repos
    carrying every contributor signature were marked for deletion."""
    # Arrange
    branch = facts("cla-signatures")
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.reason == KEEP_PROTECTED


def test_bare_cla_is_protected_too():
    """THE REHEARSAL FINDING'S MIRROR IMAGE, caught by running the remote
    leg in dry-run against this repository's own origin.

    The near-miss was reported as "`^cla$` misses `cla-signatures`", so
    the first protected set here listed `cla-signatures` alone — and the
    rehearsal then proposed deleting `origin/cla`, which in scitex-dev
    is ALSO a signature store: its tip is "chore(cla): create the
    signature store the org CLA workflow requires" and its tree is the
    same `signatures/cla.json`. One org, one CLA workflow, two spellings.
    """
    # Arrange
    branch = facts("cla")
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.reason == KEEP_PROTECTED


def test_claude_sweep_branches_are_not_protected():
    """THE REPAIR THAT WENT TOO FAR: `cla*` matched `claude/*`, which is
    precisely the garbage the sweep exists to collect."""
    # Arrange
    branch = facts("claude/sweep-1")
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.drop is True


def test_develop_is_protected_however_stale():
    """Age is exactly what does not decide the protected names."""
    # Arrange
    branch = facts("develop", last_commit_epoch=0.0)
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.drop is False


def test_master_is_protected_alongside_main():
    """Several repositories on the fleet still spell it `master`."""
    # Arrange
    branch = facts("master")
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.reason == KEEP_PROTECTED


# ------------------------------------------------------------------ #
# Pull requests — unknown is checked above every drop reason.          #
# ------------------------------------------------------------------ #


def test_open_pr_head_is_kept_however_stale():
    """Deleting it CLOSES the PR and destroys the review with it."""
    # Arrange
    branch = facts("feat/reviewed", has_open_pr=True, last_commit_epoch=0.0)
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.reason == KEEP_OPEN_PR


def test_unknown_pr_state_is_kept_even_when_merged_says_drop():
    """A half-answer must not license the outcome with no recovery."""
    # Arrange
    branch = facts("feat/half-answer", has_open_pr=None, merged=True)
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.reason == KEEP_PR_UNKNOWN


# ------------------------------------------------------------------ #
# Merged beats recency; recency beats nothing.                        #
# ------------------------------------------------------------------ #


def test_merged_branch_drops_however_recently_touched():
    """Without this the keep set was 16 across 6 repos; with it, 1."""
    # Arrange
    branch = facts("feat/landed", merged=True, last_commit_epoch=NOW - 60.0)
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.reason == DROP_MERGED


def test_recent_unmerged_branch_is_kept():
    """Work in flight."""
    # Arrange
    branch = facts("feat/today", last_commit_epoch=NOW - HOUR)
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.reason == KEEP_RECENT


def test_branch_exactly_at_the_window_is_dropped():
    """The window is exclusive at its far edge; pinned so nobody
    re-derives it from the prose."""
    # Arrange
    branch = facts("feat/boundary", last_commit_epoch=NOW - 24 * HOUR)
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.reason == DROP_STALE


def test_a_fresh_reflog_keeps_an_ancient_tip():
    """A branch created minutes ago off an old base is NOT stale."""
    # Arrange
    branch = facts("feat/new-off-old", last_move_epoch=NOW - 60.0)
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.reason == KEEP_RECENT


def test_unmeasurable_age_is_kept():
    """An unreadable ref is not an ancient one."""
    # Arrange
    branch = facts("feat/dateless", last_commit_epoch=None)
    # Act
    verdict = classify(branch, now=NOW)
    # Assert
    assert verdict.reason == KEEP_AGE_UNKNOWN


# ------------------------------------------------------------------ #
# Worktrees — the three shapes, told apart.                           #
# ------------------------------------------------------------------ #


def test_clean_worktree_is_removed_without_force():
    """The refusal fires on uncommitted work, so a clean tree just goes."""
    # Arrange
    branch = facts("feat/done", worktree_path="/wt", worktree_dirty=False)
    # Act
    action, _ = worktree_plan(branch, now=NOW)
    # Assert
    assert action == WT_REMOVE


def test_dirty_worktree_touched_recently_keeps_both():
    """THE UNRECOVERABLE CASE. The tip commit is 100 hours old and the
    FILES were edited a minute ago; dating this on the branch would
    force away an edit nobody has committed anywhere."""
    # Arrange
    branch = facts(
        "feat/in-progress",
        worktree_path="/wt",
        worktree_dirty=True,
        worktree_touch_epoch=NOW - 60.0,
    )
    # Act
    action, reason = worktree_plan(branch, now=NOW)
    # Assert
    assert (action, reason) == (WT_KEEP, KEEP_WORKTREE_BUSY)


def test_dirty_worktree_untouched_past_the_window_is_forced():
    """Orphaned garbage — authorised, and named in the report."""
    # Arrange
    branch = facts(
        "feat/abandoned",
        worktree_path="/wt",
        worktree_dirty=True,
        worktree_touch_epoch=NOW - 100 * HOUR,
    )
    # Act
    action, _ = worktree_plan(branch, now=NOW)
    # Assert
    assert action == WT_REMOVE_FORCE


def test_unmeasurable_worktree_state_keeps_both():
    """Same posture as every other unknown in this module."""
    # Arrange
    branch = facts("feat/opaque", worktree_path="/wt", worktree_dirty=None)
    # Act
    action, reason = worktree_plan(branch, now=NOW)
    # Assert
    assert (action, reason) == (WT_KEEP, KEEP_WORKTREE_UNKNOWN)


def test_a_dirty_worktree_with_no_file_dates_keeps_both():
    """Nothing could be stat'ed, so the force decision has no instrument."""
    # Arrange
    branch = facts(
        "feat/undatable",
        worktree_path="/wt",
        worktree_dirty=True,
        worktree_touch_epoch=None,
    )
    # Act
    action, reason = worktree_plan(branch, now=NOW)
    # Assert
    assert (action, reason) == (WT_KEEP, KEEP_WORKTREE_UNKNOWN)


def test_the_primary_checkout_is_never_removed():
    """Removing it would delete the repository."""
    # Arrange
    branch = facts(
        "feat/checked-out",
        worktree_path="/repo",
        worktree_is_primary=True,
        worktree_dirty=False,
    )
    # Act
    verdict = decide(branch, now=NOW)
    # Assert
    assert verdict.reason == KEEP_CURRENT_HEAD


def test_a_branch_with_no_worktree_plans_nothing():
    """The common case costs no extra step."""
    # Arrange
    branch = facts("feat/free")
    # Act
    action, _ = worktree_plan(branch, now=NOW)
    # Assert
    assert action == WT_NONE


def test_decide_carries_the_worktree_action_onto_the_verdict():
    """The engine acts on the verdict, so the plan must travel with it."""
    # Arrange
    branch = facts("feat/done", worktree_path="/wt", worktree_dirty=False)
    # Act
    verdict = decide(branch, now=NOW)
    # Assert
    assert verdict.worktree_action == WT_REMOVE


# ------------------------------------------------------------------ #
# The remote leg's one extra refusal.                                 #
# ------------------------------------------------------------------ #


def test_a_remote_branch_named_origin_is_reported_not_pushed():
    """`git push origin --delete origin` is ambiguous and fails; that is
    a permanent property of the NAME, so it is never retried."""
    # Arrange
    branch = facts("origin")
    # Act
    verdict = decide_remote(branch, now=NOW)
    # Assert
    assert verdict.reason == KEEP_AMBIGUOUS_NAME


def test_a_normal_remote_branch_still_drops():
    """The ambiguity guard must not shadow the ordinary case."""
    # Arrange
    branch = facts("feat/gone")
    # Act
    verdict = decide_remote(branch, now=NOW)
    # Assert
    assert verdict.reason == DROP_STALE


# EOF
