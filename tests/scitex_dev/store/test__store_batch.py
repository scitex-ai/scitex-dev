#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``Store.batch`` — one transaction instead of one per statement.

Both dialects connect in autocommit, which is right for a single interactive
write and wrong for bulk work: one logical op costs three statements and so
three durable commits. Measured adopting the real 3,712-card board, that is
18.59 ms/op against 2.06 ms/op — a 9.0x difference paid again on every
replay catch-up.

The tests here are about BEHAVIOUR, not speed. A timing assertion would be
flaky on a shared machine and would not catch the thing that actually
matters: that a failed batch leaves nothing behind.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from scitex_dev.store import NEW_RECORD, OplogGapError, replay


def _error_from(call: Callable[[], Any]) -> "BaseException | None":
    """Run ``call`` and hand back whatever it raised, or ``None``."""
    try:
        call()
    except BaseException as exc:  # noqa: BLE001 - the point is to capture any
        return exc
    return None


def test_batch_commits_the_writes_made_inside_it(local):
    # Arrange
    key = ("b0",)
    # Act
    with local.batch():
        local.put({"id": "b0", "status": "open"}, expected_revision=NEW_RECORD)
    # Assert
    assert local.get(key) is not None


def test_batch_rolls_back_every_write_when_the_body_raises(local):
    # Arrange
    boom = RuntimeError("deliberate")

    def _write_then_fail() -> None:
        with local.batch():
            local.put({"id": "b1", "status": "open"}, expected_revision=NEW_RECORD)
            raise boom

    # Act
    _error_from(_write_then_fail)
    # Assert
    assert local.get(("b1",)) is None


def test_batch_re_raises_the_original_error(local):
    # Arrange
    boom = RuntimeError("deliberate")

    def _write_then_fail() -> None:
        with local.batch():
            local.put({"id": "b2", "status": "open"}, expected_revision=NEW_RECORD)
            raise boom

    # Act
    caught = _error_from(_write_then_fail)
    # Assert
    assert caught is boom


def test_a_rolled_back_batch_leaves_no_oplog_entry(local):
    # Arrange
    def _write_then_fail() -> None:
        with local.batch():
            local.put({"id": "b3", "status": "open"}, expected_revision=NEW_RECORD)
            raise RuntimeError("deliberate")

    # Act
    _error_from(_write_then_fail)
    # Assert — the row is gone, so its op must be gone too
    assert local.origins().get(local.node, 0) == 0


def test_nested_batches_do_not_raise(local):
    # Arrange — install_genesis batches and calls replay, which batches too
    def _nested() -> None:
        with local.batch():
            with local.batch():
                local.put(
                    {"id": "b4", "status": "open"}, expected_revision=NEW_RECORD
                )

    # Act
    caught = _error_from(_nested)
    # Assert
    assert caught is None


def test_the_inner_batch_does_not_commit_early(local):
    # Arrange — inner block completes, then the OUTER one fails
    def _inner_ok_outer_fails() -> None:
        with local.batch():
            with local.batch():
                local.put(
                    {"id": "b5", "status": "open"}, expected_revision=NEW_RECORD
                )
            raise RuntimeError("deliberate")

    # Act
    _error_from(_inner_ok_outer_fails)
    # Assert — a nested COMMIT would have made this row survive
    assert local.get(("b5",)) is None


def test_a_write_after_a_rolled_back_batch_still_works(local):
    # Arrange — a botched ROLLBACK would leave the connection unusable
    def _fail() -> None:
        with local.batch():
            local.put({"id": "b6", "status": "open"}, expected_revision=NEW_RECORD)
            raise RuntimeError("deliberate")

    _error_from(_fail)
    # Act
    local.put({"id": "b7", "status": "open"}, expected_revision=NEW_RECORD)
    # Assert
    assert local.get(("b7",)) is not None


def test_a_rejected_replay_leaves_the_cursor_untouched(local, peer):
    # Arrange — a batch with a hole, which assert_contiguous refuses
    peer.put({"id": "p0", "status": "open"}, expected_revision=NEW_RECORD)
    peer.put({"id": "p1", "status": "open"}, expected_revision=NEW_RECORD)
    gapped = peer.changes_since(peer.node, 0)[1:]
    # Act
    _error_from(lambda: replay(local, peer.node, gapped))
    # Assert
    assert local.cursor(peer.node) == 0


def test_a_rejected_replay_is_an_oplog_gap_error(local, peer):
    # Arrange
    peer.put({"id": "p2", "status": "open"}, expected_revision=NEW_RECORD)
    peer.put({"id": "p3", "status": "open"}, expected_revision=NEW_RECORD)
    gapped = peer.changes_since(peer.node, 0)[1:]
    # Act
    caught = _error_from(lambda: replay(local, peer.node, gapped))
    # Assert
    assert isinstance(caught, OplogGapError)


def test_replay_inside_a_transaction_still_applies_everything(local, peer):
    # Arrange
    for index in range(5):
        peer.put({"id": f"r{index}", "status": "open"}, expected_revision=NEW_RECORD)
    entries = peer.changes_since(peer.node, 0)
    # Act
    result = replay(local, peer.node, entries)
    # Assert
    assert result.applied == 5


def test_replay_advances_the_cursor_to_the_last_entry(local, peer):
    # Arrange
    for index in range(5):
        peer.put({"id": f"s{index}", "status": "open"}, expected_revision=NEW_RECORD)
    entries = peer.changes_since(peer.node, 0)
    # Act
    replay(local, peer.node, entries)
    # Assert
    assert local.cursor(peer.node) == 5

# EOF
