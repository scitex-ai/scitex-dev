#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Postgres dialect — the advanced backend.

Use it when a store outgrows one file: several hosts writing concurrently
against the same database, or a dataset that wants real indexes and a
query planner. Everything above the dialect is identical — the same
schema, the same oplog, the same directed replay.

The driver is optional. ``psycopg`` (v3) is imported inside
:meth:`PostgresDialect.connect`, and its absence raises
:class:`~.._errors.DialectUnavailableError` naming the extra to install.
It never degrades to SQLite: a caller asking for a shared database and
receiving a private local file would watch every write succeed while no
peer ever saw one.
"""

from __future__ import annotations

from typing import Any, Final, Sequence

from .._errors import DialectUnavailableError, StoreTargetError
from .._policy import FieldKind
from .._target import Backend, StoreTarget
from . import Dialect

__all__ = ["PostgresDialect"]

_TYPES: Final[dict[FieldKind, str]] = {
    FieldKind.TEXT: "TEXT",
    FieldKind.INTEGER: "BIGINT",
    FieldKind.REAL: "DOUBLE PRECISION",
    FieldKind.BOOL: "BOOLEAN",
    FieldKind.JSON: "JSONB",
    FieldKind.BLOB: "BYTEA",
}


class PostgresDialect(Dialect):
    """Speaks Postgres. Stateless."""

    backend = Backend.POSTGRES

    def connect(self, target: StoreTarget) -> Any:
        """Open a psycopg connection to ``target``'s DSN."""
        if target.backend is not Backend.POSTGRES:  # pragma: no cover
            raise StoreTargetError(
                f"PostgresDialect received {target.describe()}."
            )
        try:
            import psycopg
        except ImportError:
            raise DialectUnavailableError(
                "The Postgres backend needs the 'psycopg' driver, which is "
                "not installed. Install it with `pip install "
                "'scitex-dev[postgres]'` (or `pip install psycopg[binary]`). "
                "This is NOT falling back to SQLite: you asked for a shared "
                "database, and a private local file would accept every write "
                "while no other host ever saw one."
            ) from None

        try:
            # `.dsn` by name — `str(locator)` renders a credential-free
            # summary precisely so a password cannot reach a log line.
            connection = psycopg.connect(target.dsn, autocommit=True)
        except Exception as exc:
            raise StoreTargetError(
                f"Cannot connect to Postgres store {target.name!r} at "
                f"{target.locator}: {exc}. "
                "Check the DSN host/port/database and that the role has "
                "CREATE rights — the store creates its tables on first use."
            ) from None
        return connection

    def placeholder(self, index: int) -> str:
        return "%s"

    def quote(self, identifier: str) -> str:
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    def column_type(self, kind: FieldKind) -> str:
        return _TYPES[kind]

    def upsert_sql(self, table: str, columns: Sequence[str], key: str) -> str:
        """``INSERT ... ON CONFLICT (key) DO UPDATE``."""
        column_list = ", ".join(self.quote(c) for c in columns)
        updates = ", ".join(
            f"{self.quote(c)} = EXCLUDED.{self.quote(c)}"
            for c in columns
            if c != key
        )
        return (
            f"INSERT INTO {self.quote(table)} ({column_list}) "
            f"VALUES ({self.placeholders(len(columns))}) "
            f"ON CONFLICT ({self.quote(key)}) DO UPDATE SET {updates}"
        )

    def to_db_bool(self, value: bool) -> Any:
        return bool(value)

    def from_db_bool(self, value: Any) -> bool:
        return bool(value)

# EOF
