#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The five safety legs, against a REAL repository.

The two tests that matter most are ``test_ancient_commit_with_fresh_reflog
_reads_as_young`` (the incident shape) and
``test_multi_commit_squash_is_landed_via_merged_pr`` (the recall shape).
Everything else pins a boundary around them.
"""

from __future__ import annotations

import time

from .conftest import future_now, merged_pr_for, no_open_pr

from scitex_dev.hygiene._branch_gc_model import (
    KEEP_ACTIVE_WORK,
    KEEP_ACTIVE_WORK_UNKNOWN,
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
    BranchInfo,
)
from scitex_dev.hygiene._branch_gc_predicate import (
    is_landed,
    is_not_active,
    is_old_enough,
    is_unchecked_out,
    is_unprotected,
    verdict_for,
)

_NO_PR = merged_pr_for()


# --------------------------------------------------------------------------
# Leg 1 — LANDED, three sources.
# --------------------------------------------------------------------------


def test_no_ff_merged_branch_is_landed_by_ancestor(repo):
    """The cheap local source answers first when it can."""
    # Arrange
    # Act
    landed = is_landed(repo, "feature/landed-ff", _NO_PR)
    # Assert
    assert landed.source == LANDED_BY_ANCESTOR


def test_cherry_picked_branch_is_landed_by_patch_equivalence(repo):
    """A rebase/cherry-pick landing is invisible to ancestry, visible to cherry."""
    # Arrange
    # Act
    landed = is_landed(repo, "feature/picked", _NO_PR)
    # Assert
    assert landed.source == LANDED_BY_PATCH_EQUIVALENCE


def test_multi_commit_squash_is_not_landed_by_either_local_source(repo):
    """THE RECALL GAP: no local source can see a multi-commit squash.

    This is why `git branch --merged` alone is wrong and why the merged-PR
    source is not optional. With gh answering "no", the branch reads as
    NOT landed even though its work is demonstrably on develop.
    """
    # Arrange
    # Act
    landed = is_landed(repo, "feature/squashed", _NO_PR)
    # Assert
    assert landed.value is False


def test_multi_commit_squash_is_landed_via_merged_pr(repo):
    """...and the third source closes exactly that gap."""
    # Arrange
    pr_merged = merged_pr_for("feature/squashed")
    # Act
    landed = is_landed(repo, "feature/squashed", pr_merged)
    # Assert
    assert landed.source == LANDED_BY_MERGED_PR


def test_unlanded_branch_is_not_landed(repo):
    """POSITIVE CONTROL for the negative: a real unlanded branch says False."""
    # Arrange
    # Act
    landed = is_landed(repo, "feature/unlanded", _NO_PR)
    # Assert
    assert landed.reason == KEEP_NOT_LANDED


def test_unknown_pr_state_yields_landed_unknown_not_false(repo):
    """gh answering NOTHING is UNKNOWN — never "no merged PR"."""

    # Arrange
    def unknown(_repo, _branch):
        return None

    # Act
    landed = is_landed(repo, "feature/unlanded", unknown)
    # Assert
    assert landed.reason == KEEP_LANDED_UNKNOWN


def test_raising_pr_lookup_yields_unknown_not_a_crash(repo):
    """A seam that raises degrades to UNKNOWN, never out of the pass."""

    # Arrange
    def boom(_repo, _branch):
        raise RuntimeError("gh exploded")

    # Act
    landed = is_landed(repo, "feature/unlanded", boom)
    # Assert
    assert landed.value is None


# --------------------------------------------------------------------------
# Leg 2 — THE AGE FLOOR. The property whose absence destroyed 7 branches.
# --------------------------------------------------------------------------


def test_ancient_commit_with_fresh_reflog_reads_as_young(repo):
    """THE INCIDENT SHAPE, pinned.

    `relocation/residency` points at a commit from 2001, but the ref was
    created in this clone seconds ago. Commit time alone calls it ancient;
    taking the CONSERVATIVE of both signals calls it young, which is what
    keeps it. Neutering the age floor makes this test fail — that is the
    negative control this property is worth.
    """
    # Arrange
    # Act
    ok, reason = is_old_enough(repo, "relocation/residency", 30.0, time.time())
    # Assert
    assert (ok, reason) == (False, KEEP_TOO_YOUNG)


def test_the_same_ancient_branch_reads_old_once_its_reflog_ages(repo):
    """POSITIVE CONTROL for the leg above.

    Same branch, same ancient commit — only the clock moves past the fresh
    reflog entry, and now it reads OLD. Without this, the incident test
    would also pass on an age leg hard-wired to False.
    """
    # Arrange
    # Act
    ok, _ = is_old_enough(repo, "relocation/residency", 30.0, future_now())
    # Assert
    assert ok is True


def test_branch_with_two_ancient_signals_is_old_at_real_now(repo):
    """A branch nobody has touched in this clone reads old without a fake clock."""
    # Arrange
    # Act
    ok, _ = is_old_enough(repo, "feature/landed-ff", 30.0, time.time())
    # Assert
    assert ok is True


def test_unreadable_ref_age_is_unknown_not_old(repo):
    """A ref we cannot time is UNKNOWN, and unknown keeps."""
    # Arrange
    # Act
    ok, _ = is_old_enough(repo, "no/such/branch", 30.0, future_now())
    # Assert
    assert ok is None


# --------------------------------------------------------------------------
# Leg 3 — checked out anywhere.
# --------------------------------------------------------------------------


def test_checked_out_branch_is_kept(repo):
    """develop is the fixture's HEAD, so it is never a candidate."""
    # Arrange
    heads = {"develop"}
    # Act
    ok, reason = is_unchecked_out("develop", heads)
    # Assert
    assert (ok, reason) == (False, KEEP_CHECKED_OUT)


def test_unreadable_worktree_listing_is_unknown_not_empty(repo):
    """`None` heads must not read as "nothing is checked out"."""
    # Arrange
    # Act
    ok, _ = is_unchecked_out("feature/landed-ff", None)
    # Assert
    assert ok is None


# --------------------------------------------------------------------------
# Leg 4 — protected names and open PRs.
# --------------------------------------------------------------------------


def test_release_branch_is_protected(repo):
    """release/* is protected — the gap in the pre-existing PROTECTED set."""
    # Arrange
    # Act
    ok, reason = is_unprotected(repo, "release/1.0", no_open_pr)
    # Assert
    assert (ok, reason) == (False, KEEP_PROTECTED)


def test_configured_extra_glob_widens_protection(repo):
    """Repo config may ADD to the shield."""
    # Arrange
    # Act
    ok, reason = is_unprotected(
        repo, "relocation/residency", no_open_pr, ("relocation/*",)
    )
    # Assert
    assert (ok, reason) == (False, KEEP_PROTECTED)


def test_open_pr_keeps_the_branch(repo):
    """A branch with a live PR is never deletable."""

    # Arrange
    def has_open(_repo, _branch):
        return True

    # Act
    ok, reason = is_unprotected(repo, "feature/landed-ff", has_open)
    # Assert
    assert (ok, reason) == (False, KEEP_OPEN_PR)


def test_unknown_pr_state_keeps_the_branch(repo):
    """A PR state we could not determine keeps, matching _prune_merged."""

    # Arrange
    def unknown(_repo, _branch):
        return None

    # Act
    ok, reason = is_unprotected(repo, "feature/landed-ff", unknown)
    # Assert
    assert (ok, reason) == (None, KEEP_PR_STATE_UNKNOWN)


# --------------------------------------------------------------------------
# Leg 5 — active substrate.
# --------------------------------------------------------------------------


def test_branch_named_by_an_active_card_is_kept():
    """The leg the incident actually needed."""
    # Arrange
    tokens = {"relocation-residency-20260808"}
    # Act
    ok, reason = is_not_active("relocation/residency", tokens)
    # Assert
    assert (ok, reason) == (False, KEEP_ACTIVE_WORK)


def test_unavailable_active_signal_is_unknown_not_empty():
    """`None` tokens are UNAVAILABLE — never "the fleet is doing nothing"."""
    # Arrange
    # Act
    ok, reason = is_not_active("feature/landed-ff", None)
    # Assert
    assert (ok, reason) == (None, KEEP_ACTIVE_WORK_UNKNOWN)


def test_unrelated_branch_passes_the_active_leg():
    """POSITIVE CONTROL: the leg is not hard-wired to keep everything."""
    # Arrange
    tokens = {"some-unrelated-card-id"}
    # Act
    ok, _ = is_not_active("feature/landed-ff", tokens)
    # Assert
    assert ok is True


# --------------------------------------------------------------------------
# verdict_for — every reason collected, no leg short-circuits.
# --------------------------------------------------------------------------


def test_verdict_collects_every_failing_reason_not_just_the_first(repo):
    """An operator needs the whole picture, not the first thing that failed."""
    # Arrange
    info = BranchInfo(name="feature/unlanded", sha="")
    # Act
    verdict = verdict_for(
        repo,
        info,
        min_age_days=30.0,
        now=time.time(),
        pr_merged=_NO_PR,
        pr_open=no_open_pr,
        heads={"feature/unlanded"},
        active_tokens=set(),
    )
    # Assert — not landed AND checked out; both are reported, not just one.
    assert set(verdict.keep_reasons) == {KEEP_NOT_LANDED, KEEP_CHECKED_OUT}


def test_verdict_is_deletable_when_every_leg_passes(repo):
    """POSITIVE CONTROL: the predicate can say yes, or none of this means anything."""
    # Arrange
    info = BranchInfo(name="feature/landed-ff", sha="")
    # Act
    verdict = verdict_for(
        repo,
        info,
        min_age_days=30.0,
        now=time.time(),
        pr_merged=_NO_PR,
        pr_open=no_open_pr,
        heads={"develop"},
        active_tokens=set(),
    )
    # Assert
    assert verdict.deletable is True


# EOF
