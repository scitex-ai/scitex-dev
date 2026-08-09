#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where a replica's tables live, and the two dialects that can hold them.

SEAM WITH PR 1 (``StoreTarget`` / ``TableSpec`` / dialect layer)
---------------------------------------------------------------
This module is deliberately the SMALLEST target/dialect surface the oplog
needs, under names that cannot collide with PR 1's: :class:`OplogTarget`
is PR 1's ``StoreTarget`` with the field names it is expected to carry
(``dialect``, ``dsn``, ``namespace``). At reconciliation, delete
:class:`OplogTarget` and re-export ``StoreTarget`` from PR 1's
``._target`` -- the rest of this package touches only those three fields.
Likewise, the materialised-state table here is one generic
``stx_record(table_name, record_key, payload, ...)``; PR 1's ``TableSpec``
/ ``FieldPolicy`` will replace it with typed per-table storage, and only
:func:`record_apply_sql` and :func:`record_select_sql` have to change.

The DDL is written to be BYTE-IDENTICAL across SQLite and PostgreSQL --
``TEXT`` / ``BIGINT`` / ``INTEGER`` and ``ON CONFLICT ... DO UPDATE`` mean
the same thing in both. Only the parameter placeholder differs, which is
why :func:`translate` exists and why nothing else in this package needs
to know which engine it is talking to. Two defects in this house passed
196 tests and surfaced only against a live driver, so the value of one
shared statement set is that both engines execute the same text.
"""

from __future__ import annotations

from dataclasses import dataclass

from .._core.errors import ErrorCode, ScitexError

__all__ = [
    "DDL_STATEMENTS",
    "DIALECTS",
    "POSTGRES",
    "SQLITE",
    "OplogTarget",
    "connect",
    "placeholder_for",
    "record_apply_sql",
    "record_select_sql",
    "translate",
]

SQLITE = "sqlite"
POSTGRES = "postgres"
DIALECTS = (SQLITE, POSTGRES)


@dataclass(frozen=True)
class OplogTarget:
    """One replica's storage location.

    ``namespace`` isolates co-located replicas: on PostgreSQL it is a
    schema (created on connect, then pinned via ``search_path``); on
    SQLite it is unused because a separate file already IS the isolation.
    """

    dialect: str
    dsn: str
    namespace: str = ""

    def __post_init__(self) -> None:
        if self.dialect not in DIALECTS:
            raise ValueError(
                "unknown dialect {0!r}; expected one of {1}".format(
                    self.dialect, list(DIALECTS)
                )
            )


def placeholder_for(dialect: str) -> str:
    return "%s" if dialect == POSTGRES else "?"


def translate(sql: str, dialect: str) -> str:
    """Render ``?``-style SQL for ``dialect``.

    No statement in this package contains a literal ``?`` inside a string
    constant, so the substitution is total and unambiguous.
    """
    if dialect == POSTGRES:
        return sql.replace("?", "%s")
    return sql


#: Every table this layer owns. Order matters only for readability; each
#: statement is independently ``IF NOT EXISTS`` so schema setup is
#: idempotent and safe to run on every open.
DDL_STATEMENTS = (
    # The append-only log. `fence` is a COLUMN here, not a value held
    # beside the log: an op must carry the authority it was written under
    # to wherever it is replayed.
    """
    CREATE TABLE IF NOT EXISTS stx_oplog (
        origin      TEXT   NOT NULL,
        seq         BIGINT NOT NULL,
        table_name  TEXT   NOT NULL,
        record_key  TEXT   NOT NULL,
        op          TEXT   NOT NULL,
        payload     TEXT   NOT NULL,
        fence       BIGINT NOT NULL,
        ts          TEXT   NOT NULL,
        PRIMARY KEY (origin, seq)
    )
    """,
    # Highest fence ACCEPTED per origin. An op below it was authored by a
    # writer that has since been superseded.
    """
    CREATE TABLE IF NOT EXISTS stx_fence (
        origin TEXT   NOT NULL,
        fence  BIGINT NOT NULL,
        PRIMARY KEY (origin)
    )
    """,
    # The applied-intents ledger. Without it a lost ACK makes a write that
    # actually landed report as a refusal, and the caller retries a
    # completed operation.
    """
    CREATE TABLE IF NOT EXISTS stx_applied_intent (
        intent_id TEXT   NOT NULL,
        origin    TEXT   NOT NULL,
        seq       BIGINT NOT NULL,
        ts        TEXT   NOT NULL,
        PRIMARY KEY (intent_id)
    )
    """,
    # One monotone integer per origin: everything replay needs to know.
    # `last_heard_at` is what lets a read report "host B unheard-from for
    # 4h" instead of a bare "none".
    """
    CREATE TABLE IF NOT EXISTS stx_cursor (
        origin        TEXT   NOT NULL,
        applied_seq   BIGINT NOT NULL,
        last_heard_at TEXT   NOT NULL,
        PRIMARY KEY (origin)
    )
    """,
    # Materialised state (PR 1's TableSpec replaces this shape).
    """
    CREATE TABLE IF NOT EXISTS stx_record (
        table_name TEXT    NOT NULL,
        record_key TEXT    NOT NULL,
        payload    TEXT    NOT NULL,
        deleted    INTEGER NOT NULL,
        origin     TEXT    NOT NULL,
        seq        BIGINT  NOT NULL,
        updated_at TEXT    NOT NULL,
        PRIMARY KEY (table_name, record_key)
    )
    """,
)


def record_apply_sql() -> str:
    """Idempotent, monotone materialisation of one op into ``stx_record``.

    The ``WHERE stx_record.seq < excluded.seq`` guard is what makes
    replaying an op twice a no-op: the second application finds an equal
    seq, the guard is false, and the row is left exactly as it was. It
    also makes out-of-order arrival harmless rather than destructive.
    """
    return """
    INSERT INTO stx_record
        (table_name, record_key, payload, deleted, origin, seq, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (table_name, record_key) DO UPDATE SET
        payload    = excluded.payload,
        deleted    = excluded.deleted,
        origin     = excluded.origin,
        seq        = excluded.seq,
        updated_at = excluded.updated_at
    WHERE stx_record.seq < excluded.seq
    """


def record_select_sql() -> str:
    return """
    SELECT payload, deleted, origin, seq, updated_at
    FROM stx_record
    WHERE table_name = ? AND record_key = ?
    """


def connect(target: OplogTarget):
    """Open a real connection. No in-memory stand-in, no driver shim.

    The PostgreSQL driver (``psycopg``) is imported lazily and its absence
    raises with the install hint rather than degrading to SQLite -- a
    silent engine substitution would make the test suite green against an
    engine nobody asked for.
    """
    if target.dialect == SQLITE:
        import sqlite3

        conn = sqlite3.connect(target.dsn)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    try:
        import psycopg
    except Exception as exc:  # pragma: no cover - environment-dependent
        # Broad on purpose (STX-EH001): an optional driver can fail at
        # IMPORT time for reasons other than absence (a mismatched libpq,
        # a half-built wheel). All of them mean the same thing to a caller
        # -- this target is unusable -- and all of them must say so.
        raise ScitexError(
            "PostgreSQL store target requires a working psycopg driver: {0}".format(
                exc
            ),
            code=ErrorCode.DEPENDENCY,
            remediation="pip install scitex-dev[store]",
        ) from exc

    conn = psycopg.connect(target.dsn)
    if target.namespace:
        conn.execute("CREATE SCHEMA IF NOT EXISTS {0}".format(target.namespace))
        conn.execute("SET search_path TO {0}".format(target.namespace))
        conn.commit()
    return conn


# EOF
