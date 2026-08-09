#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One replica: its log, its fence column, its intents ledger, its reads.

Run against a real SQLite file AND a real PostgreSQL schema, because the
claims here are claims about what an ENGINE does -- that ``fence`` is
genuinely a column of the created table, that ``ON CONFLICT`` really is a
no-op the second time, that a positional INSERT lines up with the
positional SELECT. A stand-in would answer all three from Python.

The intents ledger gets its own section because its whole value shows up
only in the failure case it is named for: a lost ACK. The caller believes
the write was refused and sends it again; without the ledger that retry
either duplicates the op or reports a refusal for work that is already
done.
"""

from __future__ import annotations

import time

from scitex_dev.store._oplog_model import (
    OP_UPSERT,
    Op,
    SingleWriterViolationError,
)

from .conftest import TABLE

ANCIENT = "2001-09-09T00:00:00+00:00"


def _foreign_write(store, key="k1"):
    """An op authored by beta for a record alpha already owns."""
    return Op(
        origin="beta",
        seq=1,
        table_name=TABLE,
        record_key=key,
        op=OP_UPSERT,
        payload="beta-says-so",
        fence=1,
        ts=ANCIENT,
    )


def _applied(store, entry):
    """Apply an op, returning the exception instead of raising it."""
    try:
        store.apply(entry)
    except Exception as exc:
        return exc
    return None


# --- the schema the engine actually built ----------------------------------


def test_fence_is_a_column_of_the_live_oplog_table(store):
    """Asked of the ENGINE, not of the source text."""
    # Arrange
    table = "stx_oplog"
    # Act
    columns = store.columns_of(table)
    # Assert
    assert "fence" in columns


def test_the_oplog_carries_every_declared_column(store):
    # Arrange
    expected = {
        "origin",
        "seq",
        "table_name",
        "record_key",
        "op",
        "payload",
        "fence",
        "ts",
    }
    # Act
    columns = set(store.columns_of("stx_oplog"))
    # Assert
    assert expected <= columns


def test_the_applied_intent_ledger_exists(store):
    # Arrange
    table = "stx_applied_intent"
    # Act
    columns = store.columns_of(table)
    # Assert
    assert "intent_id" in columns


# --- writing ---------------------------------------------------------------


def test_the_first_op_gets_sequence_number_one(store):
    # Arrange
    key = "k1"
    # Act
    entry = store.append(TABLE, key, "v1")
    # Assert
    assert entry.seq == 1


def test_sequence_numbers_advance_by_one(store):
    # Arrange
    store.append(TABLE, "k1", "v1")
    # Act
    second = store.append(TABLE, "k2", "v2")
    # Assert
    assert second.seq == 2


def test_a_write_carries_the_current_fence(store):
    # Arrange
    store.bump_fence()
    # Act
    entry = store.append(TABLE, "k1", "v1")
    # Assert
    assert entry.fence == 2


def test_a_local_write_is_immediately_readable(store):
    # Arrange
    key = "k1"
    # Act
    store.append(TABLE, key, "v1")
    # Assert
    assert store.read(TABLE, key).payload == "v1"


def test_an_overwrite_replaces_the_payload(store):
    # Arrange
    store.append(TABLE, "k1", "v1")
    # Act
    store.append(TABLE, "k1", "v2")
    # Assert
    assert store.read(TABLE, "k1").payload == "v2"


def test_an_explicit_delete_hides_the_record(store):
    # Arrange
    store.append(TABLE, "k1", "v1")
    # Act
    store.delete(TABLE, "k1")
    # Assert
    assert store.read(TABLE, "k1").found is False


def test_a_delete_is_itself_an_op_in_the_log(store):
    # Arrange
    store.append(TABLE, "k1", "v1")
    # Act
    entry = store.delete(TABLE, "k1")
    # Assert
    assert entry.is_delete is True


# --- the applied-intents ledger --------------------------------------------


def test_a_retried_intent_does_not_append_a_second_op(store):
    """The lost-ACK case: the caller retries work that already landed."""
    # Arrange
    store.append(TABLE, "k1", "v1", intent_id="intent-1")
    # Act
    store.append(TABLE, "k1", "v1", intent_id="intent-1")
    # Assert
    assert store.max_seq(store.origin) == 1


def test_a_retried_intent_returns_the_op_that_landed(store):
    # Arrange
    first = store.append(TABLE, "k1", "v1", intent_id="intent-1")
    # Act
    again = store.append(TABLE, "k1", "v1", intent_id="intent-1")
    # Assert
    assert again == first


def test_a_recorded_intent_is_reported_as_applied(store):
    # Arrange
    store.append(TABLE, "k1", "v1", intent_id="intent-1")
    # Act
    recorded = store.has_intent("intent-1")
    # Assert
    assert recorded is True


def test_an_unseen_intent_is_not_reported_as_applied(store):
    # Arrange
    store.append(TABLE, "k1", "v1", intent_id="intent-1")
    # Act
    recorded = store.has_intent("intent-2")
    # Assert
    assert recorded is False


def test_distinct_intents_each_append_their_own_op(store):
    # Arrange
    store.append(TABLE, "k1", "v1", intent_id="intent-1")
    # Act
    store.append(TABLE, "k2", "v2", intent_id="intent-2")
    # Assert
    assert store.max_seq(store.origin) == 2


# --- single writer per record ----------------------------------------------


def test_a_second_writer_for_one_record_is_refused(store):
    # Arrange
    store.append(TABLE, "k1", "v1")
    # Act
    outcome = _applied(store, _foreign_write(store))
    # Assert
    assert isinstance(outcome, SingleWriterViolationError)


def test_the_refusal_names_the_owning_origin(store):
    # Arrange
    store.append(TABLE, "k1", "v1")
    # Act
    outcome = _applied(store, _foreign_write(store))
    # Assert
    assert "written by alpha" in str(outcome)


def test_a_foreign_write_to_an_unclaimed_record_is_fine(store):
    # Arrange
    store.append(TABLE, "k1", "v1")
    # Act
    store.apply(_foreign_write(store, key="k2"))
    # Assert
    assert store.read(TABLE, "k2").payload == "beta-says-so"


# --- idempotent apply ------------------------------------------------------


def test_applying_one_op_twice_leaves_state_unchanged(store):
    # Arrange
    entry = store.append(TABLE, "k1", "v1")
    before = store.snapshot()
    # Act
    store.apply(entry)
    # Assert
    assert store.snapshot() == before


def test_applying_one_op_twice_does_not_grow_the_log(store):
    # Arrange
    entry = store.append(TABLE, "k1", "v1")
    # Act
    store.apply(entry)
    # Assert
    assert len(store.read_since(store.origin, 0)) == 1


def test_a_stale_op_never_overwrites_a_newer_one(store):
    # Arrange
    first = store.append(TABLE, "k1", "v1")
    store.append(TABLE, "k1", "v2")
    # Act
    store.apply(first)
    # Assert
    assert store.read(TABLE, "k1").payload == "v2"


# --- reads carry their uncertainty -----------------------------------------


def test_a_read_reports_the_watermark(store):
    # Arrange
    store.append(TABLE, "k1", "v1")
    # Act
    reading = store.read(TABLE, "k1")
    # Assert
    assert reading.watermark.seq_for("alpha") == 1


def test_absence_with_every_host_heard_is_a_definite_no(store):
    # Arrange
    store.append(TABLE, "k1", "v1")
    # Act
    reading = store.read(TABLE, "missing")
    # Assert
    assert reading.value is False


def test_absence_with_a_silent_peer_is_unknown(store):
    """ "None" is not an answer while a host that could own it is quiet."""
    # Arrange
    store.set_cursor("beta", 0, heard_at=ANCIENT)
    # Act
    reading = store.read(TABLE, "missing", now=time.time())
    # Assert
    assert reading.value is None


def test_a_silent_peer_is_named_in_the_answer(store):
    # Arrange
    store.set_cursor("beta", 0, heard_at=ANCIENT)
    # Act
    reading = store.read(TABLE, "missing", now=time.time())
    # Assert
    assert "host beta unheard-from" in reading.describe()


def test_the_reading_owner_is_the_writing_origin(store):
    # Arrange
    store.append(TABLE, "k1", "v1")
    # Act
    reading = store.read(TABLE, "k1")
    # Assert
    assert reading.owner == "alpha"


# EOF
