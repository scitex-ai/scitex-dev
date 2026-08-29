#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Concurrent Store instances on ONE node must not fail on each other.

Two defects, measured 2026-08-24 on PostgreSQL 18 with no consumer code
involved (card scitex-dev-store-concurrent-writes-collide-20260824):

1. ``Store.__init__`` raced its own DDL. Eight constructors for one absent
   schema: 7 of 8 died on ``pg_type_typname_nsp_index``. ``CREATE TABLE IF
   NOT EXISTS`` is not concurrency-safe on Postgres — the table's implicit
   row TYPE collides before the name check runs.
2. Concurrent writes with DISTINCT identities collided on the oplog's
   ``(origin, seq)`` primary key: 5 of 8. ``seq`` is ``MAX(seq) + 1`` read
   then inserted, and ``Store._lock`` guards one instance only.

Both escaped as RAW driver exceptions. The fix: a dialect ``schema_lock``
around the DDL (a session advisory lock on Postgres), and a bounded
re-read-and-retry in ``Store._append`` keyed on ``Dialect.is_unique_violation``
— with a SAVEPOINT when inside ``batch()``, where a rejected INSERT would
otherwise abort the caller's transaction.

The database-backed tests need a reachable PostgreSQL and SKIP without one:
a machine with no reachable cluster cannot exercise them. Point them at a
cluster with ``SCITEX_TEST_PG_DSN`` (the PRIMARY by default — the per-host
loopback is a standby and refuses the DDL these tests need)
plus the usual ``PGUSER`` / ``PGPASSFILE``. Each test creates and drops its
own schema, so the live fleet store is never touched. The classification
tests at the bottom need no database and run everywhere.

Both defects were timing races — failure counts varied 4/8 to 7/8 run to run
— so a single green here is weaker evidence than it looks; the fix was
verified by running the original reproduction three times in a row.

PA-306: real threads, a real database, real exception objects — no mocks.
One assertion per test.
"""

from __future__ import annotations

import os
import socket
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterator

import pytest

from scitex_dev.store import (
    NEW_RECORD,
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    Schema,
    Store,
    WriterPolicy,
    host_store,
)
from scitex_dev.store._dialect import get_dialect
from scitex_dev.store._target import Backend

from .conftest import BASE_DSN  # noqa: E402 - the PRIMARY, not the loopback
THREADS = 8
NODE = socket.gethostname()


def _schema() -> Schema:
    def ident(kind: FieldKind) -> FieldPolicy:
        return FieldPolicy(
            kind=kind,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
            indexed=False,
        )

    def fact(kind: FieldKind) -> FieldPolicy:
        return FieldPolicy(
            kind=kind,
            role=FieldRole.DATA,
            required=True,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        )

    return Schema(
        name="conc_seq",
        fields={"k": ident(FieldKind.INTEGER), "v": fact(FieldKind.TEXT)},
    )


def _open(target, schema: Schema) -> Store:
    return Store(
        target,
        schema,
        node=NODE,
        writer_policy=WriterPolicy.SINGLE_WRITER,
        actor="test",
    )


def _failures(fn: Callable[[int], "str | None"]) -> list[str]:
    """Run ``fn`` on THREADS threads at once; its non-None returns are failures."""
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        return [r for r in pool.map(fn, range(THREADS)) if r]


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}"


@pytest.fixture
def pg_target() -> Iterator:
    """A ``host_store`` target inside a throwaway schema on a real cluster.

    SKIPS — never fails — when the cluster is unreachable or refuses the
    credential. Real ``os.environ`` save/restore rather than monkeypatch:
    the point is that the REAL resolver reads the REAL variable.
    """
    psycopg = pytest.importorskip("psycopg")
    name = f"test_store_conc_{uuid.uuid4().hex[:12]}"
    try:
        with psycopg.connect(BASE_DSN, connect_timeout=5, autocommit=True) as conn:
            conn.execute(f'CREATE SCHEMA "{name}"')
    except psycopg.OperationalError as exc:
        pytest.skip(
            f"no usable PostgreSQL at {BASE_DSN}: {str(exc).splitlines()[0]}"
        )
    saved = os.environ.get("SCITEX_STORE_DSN")
    os.environ["SCITEX_STORE_DSN"] = f"{BASE_DSN}?options=-csearch_path%3D{name}"
    try:
        yield host_store(pkg="test_conc", name="conc_seq")
    finally:
        if saved is None:
            os.environ.pop("SCITEX_STORE_DSN", None)
        else:
            os.environ["SCITEX_STORE_DSN"] = saved
        with psycopg.connect(BASE_DSN, connect_timeout=5, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


# ---------------------------------------------------------------------------
# defect 1 — construction races its own DDL
# ---------------------------------------------------------------------------


def test_eight_constructors_for_an_absent_schema_all_succeed(pg_target):
    # Arrange — nothing has created the tables yet; every constructor races.
    schema = _schema()

    def construct(_i: int) -> "str | None":
        try:
            _open(pg_target, schema).close()
        except Exception as exc:  # noqa: BLE001 - the raw escape IS the defect
            return _describe(exc)
        return None

    # Act
    failures = _failures(construct)
    # Assert
    assert failures == []


def test_the_schema_lock_is_released_before_init_returns(pg_target):
    # Arrange — a lock left behind would serialise every later constructor on
    # this session forever; pg_locks for THIS backend is where it would show.
    store = _open(pg_target, _schema())
    # Act
    held = store._connection.execute(
        "SELECT count(*) AS n FROM pg_locks "
        "WHERE pid = pg_backend_pid() AND locktype = 'advisory'"
    ).fetchone()["n"]
    store.close()
    # Assert
    assert held == 0


# ---------------------------------------------------------------------------
# defect 2 — concurrent same-node writes race the (origin, seq) key
# ---------------------------------------------------------------------------


def test_eight_distinct_writes_from_eight_stores_all_land(pg_target):
    # Arrange — one serial construction so the tables exist and ONLY the
    # write races (defect 1 would otherwise hide defect 2).
    schema = _schema()
    _open(pg_target, schema).close()

    def write(i: int) -> "str | None":
        store = _open(pg_target, schema)
        try:
            store.put({"k": i, "v": "x"}, expected_revision=NEW_RECORD)
        except Exception as exc:  # noqa: BLE001
            return _describe(exc)
        finally:
            store.close()
        return None

    # Act
    failures = _failures(write)
    # Assert
    assert failures == []


def test_concurrent_writes_leave_the_oplog_contiguous(pg_target):
    # Arrange — the retry must neither skip a seq nor reuse one. Read the
    # oplog itself rather than assume how many ops one put appends.
    schema = _schema()
    _open(pg_target, schema).close()

    def write(i: int) -> None:
        store = _open(pg_target, schema)
        try:
            store.put({"k": i, "v": "x"}, expected_revision=NEW_RECORD)
        finally:
            store.close()

    _failures(write)
    # Act
    reader = _open(pg_target, schema)
    table = reader.dialect.quote(reader.dialect.oplog_table(schema))
    rows = reader._connection.execute(
        f"SELECT seq FROM {table} WHERE origin = %s ORDER BY seq", (NODE,)
    ).fetchall()
    reader.close()
    seqs = [row["seq"] for row in rows]
    # Assert — exactly 1..N, no gap and no duplicate
    assert seqs == list(range(1, len(seqs) + 1))


def test_eight_concurrent_batched_writes_all_land(pg_target):
    # Arrange — inside batch() the connection is mid-transaction, where a
    # rejected INSERT would abort it; the retry must scope the loss to a
    # savepoint so the caller's batch survives.
    schema = _schema()
    _open(pg_target, schema).close()

    def write(i: int) -> "str | None":
        store = _open(pg_target, schema)
        try:
            with store.batch():
                store.put({"k": i, "v": "x"}, expected_revision=NEW_RECORD)
        except Exception as exc:  # noqa: BLE001
            return _describe(exc)
        finally:
            store.close()
        return None

    # Act
    failures = _failures(write)
    # Assert
    assert failures == []


# ---------------------------------------------------------------------------
# the classification the retry keys on — no database needed
# ---------------------------------------------------------------------------


def test_postgres_dialect_recognises_its_unique_violation():
    # Arrange
    errors = pytest.importorskip("psycopg.errors")
    exc = errors.UniqueViolation("duplicate key value violates unique constraint")
    # Act
    verdict = get_dialect(Backend.POSTGRES).is_unique_violation(exc)
    # Assert
    assert verdict is True


def test_postgres_dialect_does_not_retry_other_errors():
    # Arrange — anything that is not the PK rejection must re-raise untouched.
    exc = ValueError("not a driver error at all")
    # Act
    verdict = get_dialect(Backend.POSTGRES).is_unique_violation(exc)
    # Assert
    assert verdict is False


