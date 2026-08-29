#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for divergence detection.

The property under test throughout is that **absence is never evidence**.
Set-difference reconciliation replaced 2,159 live rows with a 5-row
document on 2026-07-19/21 by reading "present here, missing there" as a
deletion. A peer that is merely BEHIND has no op at the sequence in
question, so there is nothing to disagree with and nothing is reported.
"""

from __future__ import annotations


import pytest

from .conftest import BASE_DSN

from scitex_dev.store import (
    NEW_RECORD,
    IdentityVerdict,
    Store,
    StoreDivergedError,
    StoreTarget,
    WriterPolicy,
    detect_divergence,
)


def _dsn(schema_name: str) -> str:
    return f"{BASE_DSN}?options=-csearch_path%3D{schema_name}"


def _open(schema_name: str, card_schema) -> Store:
    return Store(
        StoreTarget.postgres(_dsn(schema_name), pkg="cards"),
        card_schema,
        node="node-a",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )


@pytest.fixture
def origin_schema(pg_schemas) -> str:
    return pg_schemas("origin")


@pytest.fixture
def origin(origin_schema, card_schema):
    """A store with three ops, whose lineage uuid has been minted."""
    store = _open(origin_schema, card_schema)
    for index in range(3):
        store.put({"id": f"c{index}", "status": "open"}, expected_revision=NEW_RECORD)
    store.identity  # mint the lineage so the copy below inherits it
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def copied(origin, origin_schema, pg_schemas, card_schema):
    """A table-for-table COPY of ``origin`` — same lineage, forked writes.

    The old fixture copied a store FILE. The analogue here is copying every
    table into a fresh schema: the lineage uuid travels with the rows, which
    is the property these tests turn on, and the two schemas then accept
    writes independently. Instance-level discrimination needs two DATABASES
    and is asserted in ``_dialect/test__postgres.py`` instead — see the note
    in ``test__identity_state``.
    """
    psycopg = pytest.importorskip("psycopg")
    origin.close()
    target_schema = pg_schemas("copy")

    # THE TABLES ARE BUILT BY THE STORE, NOT BY `CREATE TABLE AS`. The obvious
    # spelling — `CREATE TABLE copy.t AS TABLE origin.t` — copies ROWS and
    # DROPS EVERY CONSTRAINT, so the copied oplog has no ``(origin, seq)``
    # primary key and the store's own upsert then dies on
    # ``InvalidColumnReference: no unique or exclusion constraint matching the
    # ON CONFLICT specification``. Opening a store first makes the real schema,
    # constraints included; only then are the rows carried across.
    _open(target_schema, card_schema).close()

    with psycopg.connect(BASE_DSN, connect_timeout=5, autocommit=True) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s ORDER BY table_name",
                (origin_schema,),
            ).fetchall()
        ]
        for table in tables:
            columns = [
                row[0]
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s "
                    "ORDER BY ordinal_position",
                    (origin_schema, table),
                ).fetchall()
            ]
            if not columns:
                continue
            column_list = ", ".join(f'"{c}"' for c in columns)
            # The store already wrote its own lineage row when it created the
            # tables above; the origin's must WIN, because sharing the lineage
            # is the whole point of a copy.
            conn.execute(f'TRUNCATE "{target_schema}"."{table}"')
            conn.execute(
                f'INSERT INTO "{target_schema}"."{table}" ({column_list}) '
                f'SELECT {column_list} FROM "{origin_schema}"."{table}"'
            )
    store = _open(target_schema, card_schema)
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def reopened(origin, origin_schema, card_schema):
    """``origin`` re-opened after the copy was taken."""
    store = _open(origin_schema, card_schema)
    try:
        yield store
    finally:
        store.close()


def test_a_copy_shares_its_originals_lineage(copied, reopened):
    # Arrange — a uuid stored INSIDE a database cannot detect a fork of that
    # database, because the fork copies the uuid along with everything else.
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.local_identity.store_uuid == report.remote_identity.store_uuid


# THREE TESTS THAT USED TO SIT HERE ARE GONE, AND THE REASON IS THE POINT.
# They asserted that a COPY is a different INSTANCE, and they were true of a
# store file: `cp store.db store.db.bak` makes a new inode, and the inode was
# the instance id. The instance id is now `pg:<cluster>/<database>`, so two
# schemas in ONE database are the same instance — correctly. Keeping the old
# assertions would have meant asserting a fork where there is none.
#
# The behaviour they protected is not lost. That a restored dump in ANOTHER
# database reads as a different instance is what the database component of the
# identifier is FOR, and it is asserted directly against the identity SQL in
# `_dialect/test__postgres.py`, which needs no live cluster. Reproducing it
# here would need a second DATABASE, and the test role has no `rolcreatedb`
# (measured 2026-08-29) — a test that skipped on that would be worse than one
# that is honestly absent.


def test_two_schemas_in_one_database_are_the_same_instance(copied, reopened):
    # Arrange — the negative case, pinned deliberately: an ordinary second
    # schema must NOT read as a fork, or every store on the host would report
    # one and the signal would be worthless.
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.identity_verdict is IdentityVerdict.SAME


def test_an_untouched_copy_has_no_fork_point(copied, reopened):
    # Arrange — identity catches this fork BEFORE any divergence exists.
    # The log cannot: neither side has written since the split, so no
    # position was filled differently and nothing is PROVEN at the log level.
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.forks == ()


def test_a_peer_that_is_merely_behind_has_no_fork_point(copied, reopened):
    # Arrange — THE central claim. `reopened` runs ahead; `copied` simply
    # has no op at those sequences. Being behind is what a cursor is for.
    reopened.put({"id": "c9", "status": "open"}, expected_revision=NEW_RECORD)
    reopened.put({"id": "c10", "status": "open"}, expected_revision=NEW_RECORD)
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.forks == ()


def test_lag_is_reported_as_a_number_not_as_damage(peer, populated):
    # Arrange — `peer` has replayed nothing of `populated`'s fifty ops. It
    # is as far behind as a peer can be, and that is ORDINARY: it is what a
    # cursor is for.
    # Act
    report = detect_divergence(peer, populated)
    # Assert
    assert report.behind == {"local": 50}


def test_a_peer_that_has_nothing_yet_is_not_diverged(peer, populated):
    # Arrange — the inference this whole module exists to make unavailable:
    # "present here, missing there" is NOT a deletion, and fifty missing ops
    # are not damage.
    # Act
    report = detect_divergence(peer, populated)
    # Assert
    assert report.forks == ()


def test_two_writers_numbering_as_one_origin_are_proven_forked(copied, reopened):
    # Arrange — both halves mint seq 4 as node-a, with DIFFERENT content.
    # One origin cannot legitimately produce two different ops at one
    # sequence, so this is proof rather than inference.
    reopened.put({"id": "c3", "status": "open"}, expected_revision=NEW_RECORD)
    copied.put({"id": "c3", "status": "cancelled"}, expected_revision=NEW_RECORD)
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert [f.seq for f in report.forks] == [4]


def test_the_fork_point_names_the_origin_that_was_duplicated(copied, reopened):
    # Arrange
    reopened.put({"id": "c3", "status": "open"}, expected_revision=NEW_RECORD)
    copied.put({"id": "c3", "status": "cancelled"}, expected_revision=NEW_RECORD)
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.forks[0].origin == "node-a"


def test_the_earliest_disagreement_is_the_one_reported(copied, reopened):
    # Arrange — ops are immutable once written, so a fork produces an
    # agreeing PREFIX and then permanent disagreement. Agreement is monotone
    # in seq, which is what licenses the bisection.
    for index in range(3, 8):
        reopened.put({"id": f"c{index}", "status": "open"}, expected_revision=NEW_RECORD)
        copied.put({"id": f"c{index}", "status": "cancelled"}, expected_revision=NEW_RECORD)
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.forks[0].seq == 4


def test_raise_if_diverged_is_loud(copied, reopened):
    # Arrange — every failure of 2026-08-11 was silent because every call
    # reported success. This is the half that stops a caller.
    reopened.put({"id": "c3", "status": "open"}, expected_revision=NEW_RECORD)
    copied.put({"id": "c3", "status": "cancelled"}, expected_revision=NEW_RECORD)
    report = detect_divergence(reopened, copied)
    # Act
    # Assert
    with pytest.raises(StoreDivergedError, match="DIVERGED"):
        report.raise_if_diverged()


def test_raise_if_diverged_carries_the_callers_context(copied, reopened):
    # Arrange
    reopened.put({"id": "c3", "status": "open"}, expected_revision=NEW_RECORD)
    copied.put({"id": "c3", "status": "cancelled"}, expected_revision=NEW_RECORD)
    report = detect_divergence(reopened, copied)
    # Act
    # Assert
    with pytest.raises(StoreDivergedError, match="acking n-83"):
        report.raise_if_diverged(context="acking n-83")


def test_raise_if_diverged_stays_quiet_when_only_behind(peer, populated):
    # Arrange — lag must never raise. A healthy, catching-up peer that
    # looked corrupted is the mistake this module refuses to make.
    report = detect_divergence(peer, populated)
    # Act
    result = report.raise_if_diverged()
    # Assert
    assert result is None


def test_describe_names_both_sides(copied, reopened):
    # Arrange — short enough to put in a log line or a card note.
    report = detect_divergence(reopened, copied)
    # Act
    line = report.describe()
    # Assert
    assert "node-a vs node-a" in line

# EOF
