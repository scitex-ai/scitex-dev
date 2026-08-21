#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""""No PR" and "could not ask" must never parse to the same thing.

Every test here is about that one distinction, because it is the difference
between a sweep that pauses when it is blind and a sweep that deletes the
repository. The parsers are pure, so this whole path is exercised without a
repository and without the network — which is the point: the code that feeds a
branch-deleter should not need a branch-deleter to test.
"""

from __future__ import annotations

from datetime import date

from scitex_dev.branches._facts import (
    UNKNOWN_PR,
    PrState,
    build_facts,
    parse_branch_ages,
    parse_pr_states,
    parse_worktree_branches,
)

AGES = {"feat/a": date(2026, 8, 1), "feat/b": date(2026, 8, 14)}


def test_branch_ages_parse() -> None:
    # Arrange
    text = "2026-08-01 feat/a\n2026-08-14 feat/b\n"
    # Act
    ages = parse_branch_ages(text)
    # Assert
    assert ages == AGES


def test_a_malformed_age_line_is_skipped_not_defaulted() -> None:
    """A branch with no date is not swept; a branch with a WRONG date is.

    Only one of those two failures is recoverable, so the parser drops the row
    rather than inventing a stamp for it.
    """
    # Arrange
    text = "not-a-date feat/bad\n2026-08-14 feat/b\n"
    # Act
    ages = parse_branch_ages(text)
    # Assert
    assert list(ages) == ["feat/b"]


def test_a_branch_name_containing_spaces_is_kept_whole() -> None:
    """Split on the FIRST field only — git refs may carry spaces."""
    # Arrange
    text = "2026-08-14 feat/with space\n"
    # Act
    ages = parse_branch_ages(text)
    # Assert
    assert list(ages) == ["feat/with space"]


def test_worktree_branches_parse() -> None:
    # Arrange
    porcelain = (
        "worktree /repo\nHEAD abc\nbranch refs/heads/develop\n\n"
        "worktree /repo/.worktrees/x\nHEAD def\nbranch refs/heads/feat/x\n"
    )
    # Act
    branches = parse_worktree_branches(porcelain)
    # Assert
    assert branches == frozenset({"develop", "feat/x"})


def test_a_detached_worktree_pins_no_branch() -> None:
    """It holds a commit, not a branch, so it makes nothing undeletable."""
    # Arrange
    porcelain = "worktree /repo/.worktrees/d\nHEAD abc\ndetached\n"
    # Act
    branches = parse_worktree_branches(porcelain)
    # Assert
    assert branches == frozenset()


def test_two_empty_listings_are_a_real_answer() -> None:
    """`[]` means "I looked, there are none" — usable, not unknown."""
    # Arrange
    empty = "[]"
    # Act
    states = parse_pr_states(empty, empty)
    # Assert
    assert states == {}


def test_open_and_merged_are_combined_per_branch() -> None:
    # Arrange
    open_payload = '[{"headRefName": "feat/open"}]'
    merged_payload = '[{"headRefName": "feat/done"}]'
    # Act
    states = parse_pr_states(open_payload, merged_payload)
    # Assert
    assert states == {
        "feat/open": PrState(has_open_pr=True, pr_merged=False),
        "feat/done": PrState(has_open_pr=False, pr_merged=True),
    }


def test_a_branch_reopened_after_merging_reads_as_both() -> None:
    """Not exotic: a follow-up PR from the same branch after an earlier merge.

    `has_open_pr` must survive, because `classify` checks merged BEFORE open
    and would otherwise drop a branch with live review on it.
    """
    # Arrange
    payload = '[{"headRefName": "feat/x"}]'
    # Act
    states = parse_pr_states(payload, payload)
    # Assert
    assert states["feat/x"] == PrState(has_open_pr=True, pr_merged=True)


def test_unparseable_output_is_no_answer_not_an_empty_answer() -> None:
    """THE DISTINCTION THIS MODULE EXISTS FOR.

    Measured cousin, 2026-08-15: `gh api` printed a 404 body to STDOUT, an
    emptiness test never fired, and 76 repositories were recorded as having a
    variable when 8 had none. There it cost a wrong census. Here it would cost
    deleted work.
    """
    # Arrange
    junk = "gh: could not find repository"
    # Act
    states = parse_pr_states(junk, "[]")
    # Assert
    assert states is None


def test_one_bad_listing_poisons_the_pair() -> None:
    """A half-read answer is not a partial answer — it is no answer.

    A branch missing from the unread half is indistinguishable from a branch
    with no PR, which the sweep would read as permission to drop.
    """
    # Arrange
    good = '[{"headRefName": "feat/open"}]'
    # Act
    states = parse_pr_states(good, "not json")
    # Assert
    assert states is None


def test_a_json_object_is_not_a_listing() -> None:
    """`gh` emits `{"message": ...}` on some errors — valid JSON, wrong shape."""
    # Arrange
    payload = '{"message": "Not Found"}'
    # Act
    states = parse_pr_states(payload, "[]")
    # Assert
    assert states is None


def test_a_row_missing_its_head_ref_poisons_the_listing() -> None:
    """Silently skipping it would under-report open PRs — the unsafe direction."""
    # Arrange
    payload = '[{"number": 1}]'
    # Act
    states = parse_pr_states(payload, "[]")
    # Assert
    assert states is None


def test_no_pr_answer_makes_every_branch_unknown() -> None:
    """THE FAIL-SAFE. Blind must mean pause, never proceed."""
    # Arrange
    ages = AGES
    # Act
    facts = build_facts(ages, pr_states=None)
    # Assert
    assert all(
        (f.has_open_pr, f.pr_merged) == (UNKNOWN_PR.has_open_pr, UNKNOWN_PR.pr_merged)
        for f in facts
    )


def test_a_branch_absent_from_a_good_listing_has_no_pr() -> None:
    """The one place an absence legitimately means "no".

    `gh` answered; this branch simply is not in it. Judged on age from here.
    """
    # Arrange
    ages = {"feat/a": date(2026, 8, 1)}
    # Act
    facts = build_facts(ages, pr_states={})
    # Assert
    assert (facts[0].has_open_pr, facts[0].pr_merged) == (False, False)


def test_worktree_membership_reaches_the_facts() -> None:
    # Arrange
    ages = {"feat/a": date(2026, 8, 1)}
    # Act
    facts = build_facts(ages, worktree_branches=frozenset({"feat/a"}), pr_states={})
    # Assert
    assert facts[0].in_worktree is True


def test_pr_state_reaches_the_facts() -> None:
    """The positive control: without it, a builder that returned all-unknown
    would satisfy the fail-safe test and never report a real answer."""
    # Arrange
    ages = {"feat/a": date(2026, 8, 1)}
    states = {"feat/a": PrState(has_open_pr=True, pr_merged=False)}
    # Act
    facts = build_facts(ages, pr_states=states)
    # Assert
    assert facts[0].has_open_pr is True


# EOF
