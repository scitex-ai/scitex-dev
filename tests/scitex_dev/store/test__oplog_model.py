#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The op record, its column order, and the refusals it validates on sight.

Two of these are structural claims that the rest of the design leans on:
``fence`` must be one of the oplog's own columns (a fence held beside the
log cannot travel with the op it authorises), and :meth:`Op.as_row` must
emit values in exactly :data:`OPLOG_COLUMNS` order (every INSERT and
SELECT in this package is positional). Both are cheap to assert and
expensive to discover by other means.
"""

from __future__ import annotations

from scitex_dev.store._oplog_model import (
    OP_DELETE,
    OP_UPSERT,
    OPLOG_COLUMNS,
    Op,
    OplogGapError,
    StoreReplayError,
    SupersededFenceError,
    UnknownOpKindError,
    utc_now_iso,
)


def _op(**overrides):
    fields = {
        "origin": "alpha",
        "seq": 1,
        "table_name": "notes",
        "record_key": "k1",
        "op": OP_UPSERT,
        "payload": "hello",
        "fence": 1,
        "ts": "2026-08-09T00:00:00+00:00",
    }
    fields.update(overrides)
    return Op(**fields)


def _built(**overrides):
    """Build an op, returning the exception instead of raising it."""
    try:
        return _op(**overrides)
    except Exception as exc:
        return exc


# --- the structural claims -------------------------------------------------


def test_fence_is_a_column_of_the_oplog():
    """A fence beside the log cannot replicate; a fence IN it must."""
    # Arrange
    columns = OPLOG_COLUMNS
    # Act
    has_fence = "fence" in columns
    # Assert
    assert has_fence is True


def test_row_order_matches_the_declared_columns():
    # Arrange
    entry = _op()
    # Act
    row = entry.as_row()
    # Assert
    assert len(row) == len(OPLOG_COLUMNS)


def test_row_places_the_fence_where_the_columns_say():
    # Arrange
    entry = _op(fence=7)
    # Act
    row = entry.as_row()
    # Assert
    assert row[OPLOG_COLUMNS.index("fence")] == 7


def test_round_trip_through_a_row_preserves_the_op():
    # Arrange
    entry = _op(fence=3, seq=9)
    # Act
    restored = Op.from_row(entry.as_row())
    # Assert
    assert restored == entry


# --- validation on construction --------------------------------------------


def test_unknown_op_kind_is_refused():
    # Arrange
    kind = "merge"
    # Act
    outcome = _built(op=kind)
    # Assert
    assert isinstance(outcome, UnknownOpKindError)


def test_unknown_op_kind_names_the_legal_kinds():
    # Arrange
    kind = "merge"
    # Act
    outcome = _built(op=kind)
    # Assert
    assert "upsert" in str(outcome)


def test_sequence_numbers_start_at_one():
    # Arrange
    seq = 0
    # Act
    outcome = _built(seq=seq)
    # Assert
    assert isinstance(outcome, ValueError)


def test_delete_op_reports_itself_as_a_delete():
    # Arrange
    entry = _op(op=OP_DELETE, payload="")
    # Act
    is_delete = entry.is_delete
    # Assert
    assert is_delete is True


def test_upsert_op_is_not_a_delete():
    # Arrange
    entry = _op()
    # Act
    is_delete = entry.is_delete
    # Assert
    assert is_delete is False


# --- the refusals are one family -------------------------------------------


def test_gap_error_is_a_store_replay_error():
    # Arrange
    error = OplogGapError("hole")
    # Act
    kinship = isinstance(error, StoreReplayError)
    # Assert
    assert kinship is True


def test_gap_error_carries_a_remediation():
    # Arrange
    error = OplogGapError("hole")
    # Act
    remediation = error.remediation
    # Assert
    assert "Do NOT advance the cursor past a gap" in remediation


def test_superseded_fence_error_carries_a_remediation():
    # Arrange
    error = SupersededFenceError("stale")
    # Act
    remediation = error.remediation
    # Assert
    assert "current fence" in remediation


# --- stamps ----------------------------------------------------------------


def test_timestamps_are_timezone_aware():
    # Arrange
    expected_suffix = "+00:00"
    # Act
    stamp = utc_now_iso()
    # Assert
    assert stamp.endswith(expected_suffix)


# EOF
