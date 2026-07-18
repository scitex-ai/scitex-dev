#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Behavioural tests for the `pr expire` engine (`scitex_dev._ecosystem.pr_expire`).

NO mocks. The orchestrator's I/O is exercised through real in-memory fakes
that RECORD their calls, so we can assert both the outcome and — critically
for the fail-closed tests — the exact call ordering and non-calls.

Style: one assertion per test + AAA markers (STX-TQ007 / STX-TQ002).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scitex_dev._ecosystem.pr_expire import (
    ExpireResult,
    PRExpireError,
    PRInfo,
    find_expiring,
    run_expire,
)

NOW = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


def _pr(number: int, *, created_days_ago: float, updated_days_ago: float) -> PRInfo:
    return PRInfo(
        number=number,
        title=f"PR {number}",
        created_at=NOW - timedelta(days=created_days_ago),
        updated_at=NOW - timedelta(days=updated_days_ago),
        author="alice",
        head_ref=f"feature/{number}",
        url=f"https://github.com/owner/name/pull/{number}",
        body=f"body of {number}\nsecond line",
        head_sha=f"sha{number:04d}",
    )


class RecordingWriter:
    """Fake intent writer that records calls and returns a card id (or fails)."""

    def __init__(self, *, card_id="card-123", raise_exc=None, return_value=None):
        self.calls: list[tuple[str, list[PRInfo]]] = []
        self._card_id = card_id
        self._raise = raise_exc
        self._return_value = return_value

    def __call__(self, repo: str, expiring: list[PRInfo]) -> str:
        self.calls.append((repo, list(expiring)))
        if self._raise is not None:
            raise self._raise
        if self._return_value is not None:
            return self._return_value
        return self._card_id


class RecordingCloser:
    """Fake PR closer that records every (pr, comment) it is asked to close."""

    def __init__(self):
        self.calls: list[tuple[PRInfo, str]] = []

    def __call__(self, pr: PRInfo, comment: str) -> None:
        self.calls.append((pr, comment))


class OrderedRecorder:
    """Records interleaved write/close events to assert ordering."""

    def __init__(self, *, card_id="card-xyz"):
        self.order: list[str] = []
        self._card_id = card_id

    def write(self, repo, expiring):
        self.order.append("write")
        return self._card_id

    def close(self, pr, comment):
        self.order.append(f"close-{pr.number}")


def _list_fn(prs):
    return lambda repo: list(prs)


# --------------------------------------------------------------------- #
# find_expiring — PURE                                                  #
# --------------------------------------------------------------------- #
def test_find_expiring_by_created_selects_old_prs():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=0)]
    # Act
    expiring = find_expiring(prs, days=3, by="created", now=NOW)
    # Assert
    assert [p.number for p in expiring] == [1]


def test_find_expiring_by_created_excludes_young_prs():
    # Arrange
    prs = [_pr(1, created_days_ago=1, updated_days_ago=0)]
    # Act
    expiring = find_expiring(prs, days=3, by="created", now=NOW)
    # Assert
    assert expiring == []


def test_find_expiring_by_updated_uses_updated_at():
    # Arrange: created long ago, but updated recently.
    prs = [_pr(1, created_days_ago=10, updated_days_ago=1)]
    # Act
    expiring = find_expiring(prs, days=3, by="updated", now=NOW)
    # Assert
    assert expiring == []


def test_find_expiring_by_updated_selects_stale_updates():
    # Arrange
    prs = [_pr(1, created_days_ago=10, updated_days_ago=4)]
    # Act
    expiring = find_expiring(prs, days=3, by="updated", now=NOW)
    # Assert
    assert [p.number for p in expiring] == [1]


def test_find_expiring_boundary_exactly_days_is_not_expiring():
    # Arrange: age == exactly `days` is not strictly older.
    prs = [_pr(1, created_days_ago=3, updated_days_ago=3)]
    # Act
    expiring = find_expiring(prs, days=3, by="created", now=NOW)
    # Assert
    assert expiring == []


def test_find_expiring_just_over_boundary_is_expiring():
    # Arrange
    prs = [_pr(1, created_days_ago=3.001, updated_days_ago=0)]
    # Act
    expiring = find_expiring(prs, days=3, by="created", now=NOW)
    # Assert
    assert [p.number for p in expiring] == [1]


def test_find_expiring_empty_input():
    # Arrange
    prs: list[PRInfo] = []
    # Act
    expiring = find_expiring(prs, days=3, by="created", now=NOW)
    # Assert
    assert expiring == []


def test_find_expiring_rejects_bad_by():
    # Arrange
    prs: list[PRInfo] = []
    # Act
    # Assert
    with pytest.raises(ValueError):
        find_expiring(prs, days=3, by="bogus", now=NOW)


# --------------------------------------------------------------------- #
# run_expire — dry-run                                                  #
# --------------------------------------------------------------------- #
def _dry_run(prs, writer, closer):
    return run_expire(
        "owner/name", days=3, by="created", apply=False,
        list_fn=_list_fn(prs), write_intent_fn=writer, close_fn=closer, now=NOW,
    )


def test_run_expire_dry_run_mode_is_dry_run():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5)]
    # Act
    result = _dry_run(prs, RecordingWriter(), RecordingCloser())
    # Assert
    assert result.mode == "dry-run"


def test_run_expire_dry_run_counts_expiring():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5), _pr(2, created_days_ago=0, updated_days_ago=0)]
    # Act
    result = _dry_run(prs, RecordingWriter(), RecordingCloser())
    # Assert
    assert [p.number for p in result.expiring] == [1]


def test_run_expire_dry_run_writes_no_intent():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5)]
    writer = RecordingWriter()
    # Act
    _dry_run(prs, writer, RecordingCloser())
    # Assert
    assert writer.calls == []


def test_run_expire_dry_run_closes_nothing():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5)]
    closer = RecordingCloser()
    # Act
    _dry_run(prs, RecordingWriter(), closer)
    # Assert
    assert closer.calls == []


def test_run_expire_dry_run_has_no_intent_card_id():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5)]
    # Act
    result = _dry_run(prs, RecordingWriter(), RecordingCloser())
    # Assert
    assert result.intent_card_id is None


# --------------------------------------------------------------------- #
# run_expire — apply happy path                                         #
# --------------------------------------------------------------------- #
def _apply(prs, writer, closer):
    return run_expire(
        "owner/name", days=3, by="created", apply=True,
        list_fn=_list_fn(prs), write_intent_fn=writer, close_fn=closer, now=NOW,
    )


def test_run_expire_apply_writes_intent_before_any_close():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5), _pr(2, created_days_ago=9, updated_days_ago=9)]
    rec = OrderedRecorder()
    # Act
    run_expire(
        "owner/name", days=3, by="created", apply=True,
        list_fn=_list_fn(prs), write_intent_fn=rec.write, close_fn=rec.close, now=NOW,
    )
    # Assert
    assert rec.order == ["write", "close-1", "close-2"]


def test_run_expire_apply_records_intent_card_id():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5)]
    # Act
    result = _apply(prs, RecordingWriter(card_id="card-xyz"), RecordingCloser())
    # Assert
    assert result.intent_card_id == "card-xyz"


def test_run_expire_apply_closes_all_expiring():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5), _pr(2, created_days_ago=9, updated_days_ago=9)]
    # Act
    result = _apply(prs, RecordingWriter(), RecordingCloser())
    # Assert
    assert result.closed == [1, 2]


def test_run_expire_apply_no_expiring_writes_no_card():
    # Arrange
    prs = [_pr(1, created_days_ago=0, updated_days_ago=0)]
    writer = RecordingWriter()
    # Act
    _apply(prs, writer, RecordingCloser())
    # Assert
    assert writer.calls == []


def test_run_expire_apply_no_expiring_closes_nothing():
    # Arrange
    prs = [_pr(1, created_days_ago=0, updated_days_ago=0)]
    closer = RecordingCloser()
    # Act
    _apply(prs, RecordingWriter(), closer)
    # Assert
    assert closer.calls == []


def test_run_expire_apply_close_comment_references_intent_card():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5)]
    closer = RecordingCloser()
    # Act
    _apply(prs, RecordingWriter(card_id="card-abc"), closer)
    # Assert
    assert "card-abc" in closer.calls[0][1]


# --------------------------------------------------------------------- #
# run_expire — FAIL-CLOSED (load-bearing)                               #
# --------------------------------------------------------------------- #
def _apply_swallow(prs, writer, closer):
    """Run apply, swallowing the expected PRExpireError (for state asserts)."""
    try:
        _apply(prs, writer, closer)
    except PRExpireError:
        pass


def test_run_expire_fail_closed_raises_when_intent_write_raises():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5)]
    writer = RecordingWriter(raise_exc=RuntimeError("registry unavailable"))
    # Act
    # Assert
    with pytest.raises(PRExpireError):
        _apply(prs, writer, RecordingCloser())


def test_run_expire_fail_closed_never_closes_when_intent_write_raises():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5), _pr(2, created_days_ago=9, updated_days_ago=9)]
    writer = RecordingWriter(raise_exc=RuntimeError("registry unavailable"))
    closer = RecordingCloser()
    # Act
    _apply_swallow(prs, writer, closer)
    # Assert: the load-bearing invariant — no PR was closed after a write failure.
    assert closer.calls == []


def test_run_expire_fail_closed_did_attempt_the_write():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5)]
    writer = RecordingWriter(raise_exc=RuntimeError("registry unavailable"))
    # Act
    _apply_swallow(prs, writer, RecordingCloser())
    # Assert: truly a write-failure abort (the writer WAS attempted).
    assert len(writer.calls) == 1


def test_run_expire_fail_closed_raises_when_intent_write_returns_falsy():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5)]
    writer = RecordingWriter(return_value="")  # falsy id == failure
    # Act
    # Assert
    with pytest.raises(PRExpireError):
        _apply(prs, writer, RecordingCloser())


def test_run_expire_fail_closed_never_closes_when_intent_write_returns_falsy():
    # Arrange
    prs = [_pr(1, created_days_ago=5, updated_days_ago=5)]
    writer = RecordingWriter(return_value="")
    closer = RecordingCloser()
    # Act
    _apply_swallow(prs, writer, closer)
    # Assert
    assert closer.calls == []


def test_expire_result_defaults_are_empty():
    # Arrange
    res = ExpireResult(repo="r", examined=0)
    # Act
    shape = (res.expiring, res.closed, res.mode)
    # Assert
    assert shape == ([], [], "dry-run")
