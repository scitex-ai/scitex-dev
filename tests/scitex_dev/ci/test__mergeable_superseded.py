#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A successful re-run must be able to clear a failed attempt.

Measured 2026-08-09, on the v0.43.1 release itself. Two runs of the same
check name existed on ONE head commit:

    pytest-matrix-py3.12  id=93297989333  FAILURE  started 20:33:21
    pytest-matrix-py3.12  id=93297831878  SUCCESS  started 20:44:06

The first died mid-step (infrastructure: "Install dependencies" recorded no
conclusion, log blob 404). The second ran the SAME commit and passed.

`_to_checks` treated every API row as an independent check, so the dead
attempt counted forever and `ci verify` returned NOT_READY for a pull
request whose code was fine. No re-run could ever clear it — a verifier
that cannot be un-failed by a successful retry is broken exactly where
retries exist, which is infrastructure flakes.

LATEST MEANS MOST RECENTLY CREATED, NOT MOST RECENTLY STARTED, and the two
disagree here. Note the ids against the timestamps above: the FAILING run
has the HIGHER id, so it was created later; the passing one belonged to an
earlier-created workflow that sat in the queue and therefore started later.

The first version of this fix ordered by `started_at`, called the check
green, and disagreed with GitHub — which held the pull request at
mergeStateStatus=BLOCKED on the strength of the failing row. That was
caught by querying the platform instead of trusting the intuition that
"later start = newer attempt".

A verifier must model the gate that ACTUALLY decides the merge, not a more
sensible gate of its own invention. Being more permissive than branch
protection means telling someone to merge what the platform will refuse.

Unlike a silent dedupe, the superseded attempt is still REPORTED, so a
genuinely intermittent check stays visible rather than laundered into a
pass by one lucky retry.

The rows below carry the real ids and timestamps from that incident.
"""

from __future__ import annotations

from scitex_dev.ci._mergeable import _to_checks

HEAD = "c704968" + "0" * 33


def rows_with_a_failed_then_passing_retry() -> list[dict]:
    return [
        {
            "name": "pytest-matrix-on-ubuntu-py3.12",
            "id": 93297989333,
            "status": "completed",
            "conclusion": "failure",
            "head_sha": HEAD,
            "started_at": "2026-08-09T20:33:21Z",
            "completed_at": "2026-08-09T20:43:22Z",
        },
        {
            "name": "pytest-matrix-on-ubuntu-py3.12",
            "id": 93297831878,
            "status": "completed",
            "conclusion": "success",
            "head_sha": HEAD,
            "started_at": "2026-08-09T20:44:06Z",
            "completed_at": "2026-08-09T20:49:16Z",
        },
    ]


def by_state(checks, state: str):
    return [c for c in checks if c.state == state]


class TestTheMostRecentlyCreatedAttemptDecides:
    """Creation order (id), because that is what branch protection uses."""

    def test_the_lower_id_success_is_marked_superseded(self):
        """It STARTED later but was CREATED earlier — it does not win."""
        # Arrange
        rows = rows_with_a_failed_then_passing_retry()
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert by_state(checks, "SUCCESS")[0].superseded

    def test_the_higher_id_failure_remains_current(self):
        """Matching GitHub, which held this exact PR at BLOCKED."""
        # Arrange
        rows = rows_with_a_failed_then_passing_retry()
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert not by_state(checks, "FAILURE")[0].superseded

    def test_a_later_start_time_does_not_override_creation_order(self):
        """The whole point: started_at inverts the answer, and is wrong."""
        # Arrange
        rows = rows_with_a_failed_then_passing_retry()
        checks = _to_checks(rows, HEAD)
        # Act
        current = [c for c in checks if not c.superseded]
        # Assert
        assert current[0].state == "FAILURE"

    def test_order_in_the_api_response_does_not_matter(self):
        """The failing row arrived FIRST in the real response."""
        # Arrange
        rows = list(reversed(rows_with_a_failed_then_passing_retry()))
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert by_state(checks, "SUCCESS")[0].superseded

    def test_nothing_is_dropped(self):
        """Superseded is reported, not discarded — a retry must stay visible."""
        # Arrange
        rows = rows_with_a_failed_then_passing_retry()
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert len(checks) == 2


class TestASupersededAttemptSaysSo:
    def test_it_describes_itself_as_superseded(self):
        # Arrange
        rows = rows_with_a_failed_then_passing_retry()
        checks = _to_checks(rows, HEAD)
        # Act
        text = by_state(checks, "SUCCESS")[0].describe()
        # Assert
        assert "superseded" in text

    def test_it_says_which_attempt_it_was(self):
        # Arrange
        rows = rows_with_a_failed_then_passing_retry()
        checks = _to_checks(rows, HEAD)
        # Act
        text = by_state(checks, "SUCCESS")[0].describe()
        # Assert
        assert "EARLIER attempt" in text


class TestASingleAttemptIsUnaffected:
    def test_a_lone_check_is_never_marked_superseded(self):
        # Arrange
        rows = [
            {
                "name": "audit",
                "id": 1,
                "status": "completed",
                "conclusion": "success",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:33:00Z",
                "completed_at": "2026-08-09T20:34:00Z",
            }
        ]
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert not checks[0].superseded

    def test_different_names_do_not_supersede_each_other(self):
        # Arrange
        rows = [
            {
                "name": "audit",
                "id": 1,
                "status": "completed",
                "conclusion": "success",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:33:00Z",
            },
            {
                "name": "sphinx",
                "id": 2,
                "status": "completed",
                "conclusion": "failure",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:40:00Z",
            },
        ]
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert not any(c.superseded for c in checks)


class TestACancelledSupersededAttemptDoesNotBlock:
    """Checks the `cancel-in-progress` interaction, which was recorded as a
    trap and turns out to be closed by the superseded rule itself.

    `CANCELLED` is in FAILING_STATES, so before this change, adding
    `concurrency: cancel-in-progress: true` would have made every cancelled
    run count as a failure against its head — the verifier would have failed
    pull requests on the strength of the very optimisation meant to speed
    them up. That was written down as a reason NOT to add concurrency.

    But cancel-in-progress cancels the OLDER run when a newer one starts, so
    the cancelled row is always the earlier-CREATED one — exactly what the
    superseded rule discards. The trap is closed as a side effect.

    Recorded as a test rather than a note because the reasoning is only
    correct while "superseded" means created-order. If that key ever changes
    back to start time, a queued-then-cancelled run could outrank its
    replacement and this becomes wrong again.
    """

    def test_a_cancelled_earlier_run_is_superseded(self):
        # Arrange
        rows = [
            {
                "name": "tests",
                "id": 100,
                "status": "completed",
                "conclusion": "cancelled",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:30:00Z",
            },
            {
                "name": "tests",
                "id": 200,
                "status": "completed",
                "conclusion": "success",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:31:00Z",
            },
        ]
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert by_state(checks, "CANCELLED")[0].superseded

    def test_the_replacement_decides_and_it_passed(self):
        # Arrange
        rows = [
            {
                "name": "tests",
                "id": 100,
                "status": "completed",
                "conclusion": "cancelled",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:30:00Z",
            },
            {
                "name": "tests",
                "id": 200,
                "status": "completed",
                "conclusion": "success",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:31:00Z",
            },
        ]
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert [c for c in checks if not c.superseded][0].passed

    def test_a_cancelled_run_with_no_replacement_still_blocks(self):
        """Cancellation is not a pass. Nothing here waves it through."""
        # Arrange
        rows = [
            {
                "name": "tests",
                "id": 100,
                "status": "completed",
                "conclusion": "cancelled",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:30:00Z",
            }
        ]
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert not checks[0].passed


class TestAStillFailingRetryStillCounts:
    """The fix must not turn a real, repeatable failure into a pass."""

    def test_a_repeated_failure_is_not_superseded(self):
        # Arrange
        rows = [
            {
                "name": "audit",
                "id": 1,
                "status": "completed",
                "conclusion": "failure",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:33:00Z",
            },
            {
                "name": "audit",
                "id": 2,
                "status": "completed",
                "conclusion": "failure",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:44:00Z",
            },
        ]
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert not [c for c in checks if not c.superseded][0].passed

    def test_a_successful_rerun_created_later_does_clear_a_failure(self):
        """The case the fix exists for, with creation order agreeing."""
        # Arrange
        rows = [
            {
                "name": "audit",
                "id": 10,
                "status": "completed",
                "conclusion": "failure",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:33:00Z",
            },
            {
                "name": "audit",
                "id": 20,
                "status": "completed",
                "conclusion": "success",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:44:00Z",
            },
        ]
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert [c for c in checks if not c.superseded][0].passed

    def test_ids_are_compared_numerically_not_as_strings(self):
        """id 9 vs 10: string order would pick 9 and invert the answer."""
        # Arrange
        rows = [
            {
                "name": "audit",
                "id": 9,
                "status": "completed",
                "conclusion": "failure",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:33:00Z",
            },
            {
                "name": "audit",
                "id": 10,
                "status": "completed",
                "conclusion": "success",
                "head_sha": HEAD,
                "started_at": "2026-08-09T20:44:00Z",
            },
        ]
        # Act
        checks = _to_checks(rows, HEAD)
        # Assert
        assert [c for c in checks if not c.superseded][0].passed


# EOF
