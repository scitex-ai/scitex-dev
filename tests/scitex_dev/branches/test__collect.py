#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The layer that reads the world must say what it could not read.

The sweep DELETES on these facts. Measured twice on 2026-08-15 in this
repository: an audit walker returned 1142 files with `fd` present and 1227
without, and `Path.exists()` raised on one host while answering on three.
Both were environment-dependent reads that looked like facts.

So "I could not read it" is its own outcome here, never a quiet False.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev.branches._collect import (
    CollectionReport,
    collect_facts,
    render_collection,
)

_AGES = "2026-08-01 feat/alpha\n2026-08-14 main\n"
_WORKTREES = "worktree /repo\nbranch refs/heads/main\n\nworktree /repo/.worktrees/a\nbranch refs/heads/feat/alpha\n"
_OPEN = "[]"
_MERGED = '[{"headRefName": "feat/alpha"}]'


def _runner_for(table: dict[str, tuple[int, str]]):
    """A REAL callable keyed on the first two argv tokens — no patching."""

    def run(argv):
        for key, result in table.items():
            if key in " ".join(argv):
                return result
        return (0, "")

    return run


def test_a_complete_collection_reports_nothing_unreadable():
    # Arrange
    runner = _runner_for(
        {"for-each-ref": (0, _AGES), "worktree": (0, _WORKTREES), "--state open": (0, _OPEN), "--state merged": (0, _MERGED)}
    )
    # Act
    _facts, report = collect_facts(Path("/repo"), runner=runner)
    # Assert
    assert report.is_complete is True


def test_an_unreachable_gh_is_named_rather_than_swallowed():
    """THE CASE THIS MODULE EXISTS FOR. The sweep still runs — `classify`
    keeps anything it cannot judge — but the operator is told, because
    "kept 12" and "kept 12 because gh was unreachable" are different
    reports and only one is a to-do list."""
    # Arrange
    runner = _runner_for(
        {"for-each-ref": (0, _AGES), "worktree": (0, _WORKTREES), "--state open": (1, ""), "--state merged": (1, "")}
    )
    # Act
    _facts, report = collect_facts(Path("/repo"), runner=runner)
    # Assert
    assert report.unreadable == ("gh pr list",)


def test_an_unreachable_gh_still_yields_facts_to_sweep():
    """Degrade to KEEPING, not to refusing. Losing PR state costs precision,
    not the whole run."""
    # Arrange
    runner = _runner_for(
        {"for-each-ref": (0, _AGES), "worktree": (0, _WORKTREES), "--state open": (1, ""), "--state merged": (1, "")}
    )
    # Act
    facts, _report = collect_facts(Path("/repo"), runner=runner)
    # Assert
    assert len(facts) == 2


def test_a_failed_branch_list_yields_no_facts_at_all():
    """No branch list means we FAILED TO LOOK, not that everything is fine.

    Returning branches here would be inventing them; returning "clean" would
    be the sealed thermometer.
    """
    # Arrange
    runner = _runner_for({"for-each-ref": (128, "")})
    # Act
    facts, report = collect_facts(Path("/repo"), runner=runner)
    # Assert
    assert (facts, report.unreadable) == ([], ("git for-each-ref",))


def test_a_failed_worktree_list_refuses_outright():
    """THE ONE THAT MUST NOT DEGRADE GRACEFULLY.

    A branch checked out in a worktree must never be deleted, so losing this
    list would make the sweep delete MORE, not less. Every other missing
    source costs precision; this one costs safety.
    """
    # Arrange
    runner = _runner_for({"for-each-ref": (0, _AGES), "worktree": (1, "")})
    # Act
    facts, report = collect_facts(Path("/repo"), runner=runner)
    # Assert
    assert (facts, report.unreadable) == ([], ("git worktree list",))


def test_unparseable_pr_output_is_unreadable_not_empty():
    """`None` and `[]` are different answers: "could not read" versus "read,
    and there are no PRs". Collapsing them is how a broken lookup becomes a
    clean bill of health."""
    # Arrange
    runner = _runner_for(
        {
            "for-each-ref": (0, _AGES),
            "worktree": (0, _WORKTREES),
            "--state open": (0, "not json at all"), "--state merged": (0, _MERGED),
        }
    )
    # Act
    _facts, report = collect_facts(Path("/repo"), runner=runner)
    # Assert
    assert report.unreadable == ("gh pr list (unparseable output)",)


def test_the_render_names_the_source_and_the_consequence():
    """An alarm nobody can act on is one people learn to skip."""
    # Arrange
    report = CollectionReport(("gh pr list",))
    # Act
    text = render_collection(report)
    # Assert
    assert "gh pr list" in text and "INCOMPLETE" in text


def test_a_complete_render_carries_no_alarm():
    """POSITIVE CONTROL: a renderer that always warned would pass the test
    above and teach every reader to skip the line."""
    # Arrange
    report = CollectionReport(())
    # Act
    text = render_collection(report)
    # Assert
    assert "COULD NOT BE READ" not in text


# EOF
