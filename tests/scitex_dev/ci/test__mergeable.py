#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The verdict must not be misreadable — one test per way it could be.

Each class below corresponds to a real failure from 2026-08-09. The
decision logic is exercised directly through ``_decide`` and ``_to_checks``
with real API-shaped rows, so no network and no mocking of production
internals: the rows ARE the collaborator's output, hand-written from what
the API actually returns.
"""

from __future__ import annotations

import pytest

from scitex_dev.ci._mergeable import (
    EXIT_NOT_READY,
    EXIT_READY,
    EXIT_UNKNOWN,
    MergeReadiness,
    Readiness,
    _decide,
    _to_checks,
)

HEAD = "fdce9aae19bc44be244e7d85ca432c343149e698"
OTHER = "788c03b4683f17e6e7124118aa0df0b04e46b546"
CLEAN = {"mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"}


def _row(name: str, conclusion: str | None, sha: str, status: str = "completed") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion, "head_sha": sha}


class TestAnInheritedGreenIsNotAPass:
    """The week-old verdict: runs that describe a different commit."""

    def test_a_run_on_another_commit_is_marked_stale(self):
        # Arrange
        rows = [_row("audit", "success", OTHER)]
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert checks[0].stale

    def test_a_stale_green_blocks_readiness(self):
        # Arrange
        checks = _to_checks([_row("audit", "success", OTHER)], HEAD)
        # Act
        verdict = _decide("o/r#1", HEAD, checks, CLEAN)
        # Assert
        assert verdict.readiness is Readiness.NOT_READY

    def test_the_reason_names_the_commit_it_actually_ran_on(self):
        """Without the SHA the reader cannot tell which code was tested."""
        # Arrange
        checks = _to_checks([_row("audit", "success", OTHER)], HEAD)
        # Act
        verdict = _decide("o/r#1", HEAD, checks, CLEAN)
        # Assert
        assert OTHER[:7] in " ".join(verdict.reasons)

    def test_a_run_on_the_current_head_is_not_stale(self):
        # Arrange
        rows = [_row("audit", "success", HEAD)]
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert not checks[0].stale


class TestSkippedIsNotPassed:
    """The summary line folds SKIPPING into the pass total. This must not."""

    def test_a_skipped_check_does_not_count_as_passed(self):
        # Arrange
        checks = _to_checks([_row("owner-bypass", "skipped", HEAD)], HEAD)
        # Act
        passed = checks[0].passed
        # Assert
        assert not passed

    def test_a_skipped_check_alone_does_not_block(self):
        """Conditional jobs legitimately skip; only silence about it is wrong."""
        # Arrange
        checks = _to_checks(
            [_row("owner-bypass", "skipped", HEAD), _row("audit", "success", HEAD)],
            HEAD,
        )
        # Act
        verdict = _decide("o/r#1", HEAD, checks, CLEAN)
        # Assert
        assert verdict.readiness is Readiness.READY

    def test_a_skipped_check_is_still_reported(self):
        # Arrange
        checks = _to_checks(
            [_row("owner-bypass", "skipped", HEAD), _row("audit", "success", HEAD)],
            HEAD,
        )
        # Act
        verdict = _decide("o/r#1", HEAD, checks, CLEAN)
        # Assert
        assert any("owner-bypass" in r for r in verdict.reasons)


class TestNeverRanIsNotFailed:
    """Different fixes: read the log, versus find out why CI never triggered."""

    def test_no_runs_at_all_is_cannot_determine_not_not_ready(self):
        # Arrange
        checks = _to_checks([], HEAD)
        # Act
        verdict = _decide("o/r#1", HEAD, checks, CLEAN)
        # Assert
        assert verdict.readiness is Readiness.CANNOT_DETERMINE

    def test_no_runs_says_explicitly_that_this_is_not_a_pass(self):
        # Arrange
        verdict = _decide("o/r#1", HEAD, _to_checks([], HEAD), CLEAN)
        # Act
        text = " ".join(verdict.reasons)
        # Assert
        assert "not a leg that passed" in text

    def test_blocked_with_all_checks_green_reports_the_missing_required_check(self):
        """The absent required run — invisible in any list, because it is absent."""
        # Arrange
        checks = _to_checks([_row("audit", "success", HEAD)], HEAD)
        blocked = {"mergeable": "MERGEABLE", "mergeStateStatus": "BLOCKED"}
        # Act
        verdict = _decide("o/r#1", HEAD, checks, blocked)
        # Assert
        assert verdict.readiness is Readiness.NOT_READY


class TestUnknownIsNeverCollapsed:
    """Deciding either way on a missing answer is the bug this exists to stop."""

    def test_github_still_computing_is_cannot_determine(self):
        # Arrange
        checks = _to_checks([_row("audit", "success", HEAD)], HEAD)
        unknown = {"mergeable": "UNKNOWN", "mergeStateStatus": "UNKNOWN"}
        # Act
        verdict = _decide("o/r#1", HEAD, checks, unknown)
        # Assert
        assert verdict.readiness is Readiness.CANNOT_DETERMINE

    def test_cannot_determine_has_its_own_exit_code(self):
        """A script must distinguish 'no' from 'I could not tell'."""
        # Arrange
        checks = _to_checks([_row("audit", "success", HEAD)], HEAD)
        unknown = {"mergeable": "UNKNOWN", "mergeStateStatus": "UNKNOWN"}
        # Act
        verdict = _decide("o/r#1", HEAD, checks, unknown)
        # Assert
        assert verdict.exit_code == EXIT_UNKNOWN

    def test_not_ready_exit_code_differs_from_unknown(self):
        # Arrange
        checks = _to_checks([_row("audit", "failure", HEAD)], HEAD)
        # Act
        verdict = _decide("o/r#1", HEAD, checks, CLEAN)
        # Assert
        assert verdict.exit_code == EXIT_NOT_READY


class TestAPassIsAPass:
    """The tool must be usable, not merely safe."""

    def test_all_green_on_the_current_head_is_ready(self):
        # Arrange
        checks = _to_checks(
            [_row("audit", "success", HEAD), _row("sphinx", "success", HEAD)], HEAD
        )
        # Act
        verdict = _decide("o/r#1", HEAD, checks, CLEAN)
        # Assert
        assert verdict.readiness is Readiness.READY

    def test_ready_exits_zero(self):
        # Arrange
        checks = _to_checks([_row("audit", "success", HEAD)], HEAD)
        # Act
        verdict = _decide("o/r#1", HEAD, checks, CLEAN)
        # Assert
        assert verdict.exit_code == EXIT_READY


class TestStillRunningIsNotReady:
    """An unfinished check is knowable-but-not-known-yet, not unknown."""

    def test_a_queued_check_blocks(self):
        # Arrange
        rows = [_row("audit", None, HEAD, status="queued")]
        # Act
        verdict = _decide("o/r#1", HEAD, _to_checks(rows, HEAD), CLEAN)
        # Assert
        assert verdict.readiness is Readiness.NOT_READY

    def test_a_queued_check_is_not_reported_as_a_failure(self):
        # Arrange
        rows = [_row("audit", None, HEAD, status="in_progress")]
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert not checks[0].failed


class TestTheVerdictValidatesItself:
    """Malformed answers fail where built, not where acted on."""

    def test_a_bare_pr_number_is_refused(self):
        """Two repos had a #521 the same day; a number is not an identifier."""
        # Arrange
        # Act
        # Assert
        with pytest.raises(ValueError):
            MergeReadiness(readiness=Readiness.READY, pr="521", head_sha=HEAD)

    def test_a_refusal_without_reasons_is_refused(self):
        # Arrange
        # Act
        # Assert
        with pytest.raises(ValueError):
            MergeReadiness(
                readiness=Readiness.NOT_READY, pr="o/r#1", head_sha=HEAD, reasons=()
            )

    def test_a_non_enum_readiness_is_refused(self):
        """A bare string is how 'could not tell' silently becomes truthy."""
        # Arrange
        # Act
        # Assert
        with pytest.raises(ValueError):
            MergeReadiness(readiness="ready", pr="o/r#1", head_sha=HEAD)


class TestEveryFailingCheckIsListed:
    """Reporting only the first sends the reader back for a second round."""

    def test_two_failures_produce_two_reasons(self):
        # Arrange
        checks = _to_checks(
            [_row("py3.11", "failure", HEAD), _row("py3.12", "failure", HEAD)], HEAD
        )
        # Act
        verdict = _decide("o/r#1", HEAD, checks, CLEAN)
        # Assert
        assert len(verdict.reasons) == 2


# EOF
