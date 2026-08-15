#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The rule's edges, and the one that decides whether it is safe to schedule.

A sweep that deletes branches runs unattended. So the tests that matter are
not "does it drop stale work" — that is the easy half — but the four ways it
could delete something it must not: a protected branch, a checked-out branch,
a branch whose PR is open, and a branch whose PR state could not be read.
"""

from __future__ import annotations

from datetime import date

import pytest

from scitex_dev.branches import (
    INTEGRATION_BRANCHES,
    PROTECTED_BRANCHES,
    BranchFacts,
    Verdict,
    classify,
    plan_sweep,
    render_plan,
)

TODAY = date(2026, 8, 15)
OLD = date(2026, 8, 1)
FRESH = date(2026, 8, 14)


def _facts(**kw) -> BranchFacts:
    base = dict(
        name="feat/whatever",
        last_commit=OLD,
        in_worktree=False,
        has_open_pr=False,
        pr_merged=False,
    )
    base.update(kw)
    return BranchFacts(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", sorted(PROTECTED_BRANCHES))
def test_a_protected_branch_is_never_dropped_however_old(name: str) -> None:
    """`main` was 2+ months stale on this repo when the rule landed.

    Age is exactly what does NOT decide these three.
    """
    # Arrange
    facts = _facts(name=name, last_commit=date(2026, 6, 7))
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.KEEP_PROTECTED


def test_the_integration_set_is_exactly_the_operators_three() -> None:
    """A pattern would let this list grow to cover whatever is convenient."""
    # Arrange
    expected = {"main", "develop", "cla"}
    # Act
    actual = set(INTEGRATION_BRANCHES)
    # Assert
    assert actual == expected


def test_cla_signatures_is_not_dropped_however_stale() -> None:
    """THE BUG scitex-cards CAUGHT ONE DAY BEFORE IT COULD FIRE.

    `cla-signatures` is DATA the CLA workflow reads, not work. Nobody commits
    to it between uses, so it is always stale after three days — meaning the
    sweep would have dropped it in all 72 repositories, EVERY TIME, re-creating
    the org-wide CLA outage they had just spent the day repairing.

    Exact-name matching is what made it dangerous: `cla` is protected and
    `cla-signatures` is a different string.
    """
    # Arrange
    facts = _facts(name="cla-signatures", last_commit=date(2020, 1, 1))
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.KEEP_PROTECTED


def test_gh_pages_is_not_dropped_however_stale() -> None:
    """The same class, found by asking what ELSE is data rather than work.

    Nobody reported this one. A published site is written by CI and never
    worked on, so it ages exactly like `cla-signatures` and would have been
    deleted just as silently.
    """
    # Arrange
    facts = _facts(name="gh-pages", last_commit=date(2020, 1, 1))
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.KEEP_PROTECTED


def test_a_branch_merely_starting_with_a_protected_name_is_still_swept() -> None:
    """The exemption stayed EXACT — the fix is a named set, not a prefix.

    `cla-signatures` is protected because someone decided it is data. A prefix
    rule would have protected `cla-anything` including real topic branches, and
    the list would then grow by naming convention rather than by decision.
    """
    # Arrange
    facts = _facts(name="cla-fix-the-bot", last_commit=OLD)
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.DROP_STALE


def test_a_branch_checked_out_in_a_worktree_is_kept() -> None:
    """Dropping it would strand a working tree someone is mid-change in."""
    # Arrange
    facts = _facts(in_worktree=True)
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.KEEP_IN_WORKTREE


def test_an_open_pull_request_is_owed_work_not_abandoned_work() -> None:
    """The rule's answer here is finish it or drop it OUT LOUD.

    Nine such branches existed on this repo the day the rule landed. A sweep
    that ate them would have destroyed reviewed, CI-green work.
    """
    # Arrange
    facts = _facts(has_open_pr=True)
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.KEEP_OWED


def test_a_merged_pull_request_drops_at_any_age() -> None:
    """THE SQUASH-MERGE CASE, and the reason ancestry is the wrong predicate.

    Measured on this repo: `fix/declare-psycopg-in-core` had landed as #601 and
    `git branch --no-merged` still reported it unmerged, because a squash
    commit shares no history with the branch.
    """
    # Arrange
    facts = _facts(last_commit=FRESH, pr_merged=True)
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.DROP_MERGED


def test_an_unreadable_pr_state_refuses_to_judge_rather_than_guessing() -> None:
    """THE TEST THAT MAKES THIS SAFE TO SCHEDULE.

    §2: every signal is three-valued, and collapsing unknown into either pole
    is the most common bug we ship. If the GitHub lookup does not answer, the
    branch might have an OPEN pr — and deleting that is the one outcome with no
    cheap recovery. So unknown keeps, always.
    """
    # Arrange
    facts = _facts(has_open_pr=None, pr_merged=None, last_commit=date(2020, 1, 1))
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.KEEP_UNKNOWN


def test_a_half_known_pr_state_is_also_refused() -> None:
    """One field answering is not the pair answering."""
    # Arrange
    facts = _facts(has_open_pr=False, pr_merged=None)
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.KEEP_UNKNOWN


def test_unknown_outranks_merged() -> None:
    """Ordering pinned: step 3 sits ABOVE step 4 on purpose.

    A plan that read `pr_merged=True` from a partial answer would drop on the
    strength of the half it happened to get.
    """
    # Arrange
    facts = _facts(pr_merged=True, has_open_pr=None)
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.KEEP_UNKNOWN


def test_work_touched_inside_the_window_is_kept() -> None:
    # Arrange
    facts = _facts(last_commit=FRESH)
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.KEEP_FRESH


def test_exactly_three_days_is_still_fresh() -> None:
    """The boundary, stated once so nobody re-derives it from the prose.

    "not touched within the last three days" — three days IS within.
    """
    # Arrange
    facts = _facts(last_commit=date(2026, 8, 12))
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.KEEP_FRESH


def test_four_days_is_stale() -> None:
    """The other side of the same boundary — without this the rule never bites."""
    # Arrange
    facts = _facts(last_commit=date(2026, 8, 11))
    # Act
    decision = classify(facts, today=TODAY)
    # Assert
    assert decision.verdict is Verdict.DROP_STALE


def test_the_plan_reports_the_affected_set_not_only_a_count() -> None:
    """§2: "print the counts AND the affected set, not a summary you trust"."""
    # Arrange
    facts = [
        _facts(name="feat/a", last_commit=OLD),
        _facts(name="feat/b", last_commit=FRESH),
    ]
    # Act
    plan = plan_sweep(facts, today=TODAY)
    # Assert
    assert [d.name for d in plan.drops] == ["feat/a"]


def test_the_plan_is_ordered_stably() -> None:
    """An unstable order turns a re-run into a diff and hides what changed."""
    # Arrange
    facts = [_facts(name="feat/z"), _facts(name="feat/a")]
    # Act
    plan = plan_sweep(facts, today=TODAY)
    # Assert
    assert [d.name for d in plan.decisions] == ["feat/a", "feat/z"]


def test_owed_work_is_surfaced_as_its_own_list() -> None:
    # Arrange
    facts = [_facts(name="feat/owed", has_open_pr=True), _facts(name="feat/gone")]
    # Act
    plan = plan_sweep(facts, today=TODAY)
    # Assert
    assert [d.name for d in plan.owed] == ["feat/owed"]


def test_an_all_unknown_plan_warns_rather_than_reading_as_clean() -> None:
    """A sweep that could not reach GitHub must NOT look like a tidy repo."""
    # Arrange
    facts = [_facts(name="feat/a", has_open_pr=None, pr_merged=None)]
    # Act
    rendered = render_plan(plan_sweep(facts, today=TODAY))
    # Assert
    assert "could not be judged" in rendered


def test_a_clean_plan_carries_no_warning() -> None:
    """The positive control for the warning.

    Without it, a renderer that always warned would satisfy the test above and
    train every reader to ignore the line.
    """
    # Arrange
    facts = [_facts(name="feat/a", last_commit=FRESH)]
    # Act
    rendered = render_plan(plan_sweep(facts, today=TODAY))
    # Assert
    assert "could not be judged" not in rendered


def test_the_render_states_how_many_will_be_dropped() -> None:
    # Arrange
    facts = [_facts(name="feat/a", last_commit=OLD)]
    # Act
    rendered = render_plan(plan_sweep(facts, today=TODAY))
    # Assert
    assert "dropping 1" in rendered


def test_nothing_drops_when_every_branch_is_protected_or_fresh() -> None:
    """The whole-plan negative control.

    A classifier biased toward dropping would pass most tests above; this is
    the one it fails.
    """
    # Arrange
    facts = [_facts(name="main"), _facts(name="feat/new", last_commit=TODAY)]
    # Act
    plan = plan_sweep(facts, today=TODAY)
    # Assert
    assert plan.drops == ()


# EOF
