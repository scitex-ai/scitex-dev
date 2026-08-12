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

    def columns_sql(self, table: str) -> str:
        """Existing column names from `information_schema`.

        Returns zero rows for a table that does not exist, matching the
        SQLite dialect's contract — the caller reads that as "nothing to
        migrate".

        `to_regclass` is deliberately NOT used: it resolves through the
        search_path and would report a same-named table in another schema as
        this one. `information_schema.columns` filtered on `table_name` has
        the same exposure in principle, so this stays consistent with how the
        rest of this dialect addresses tables — unqualified, in whatever
        schema the connection lands. If the store ever takes a schema
        qualifier, this query and `quote` change together.
        """
        escaped = table.replace("'", "''")
        return (
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{escaped}'"
        )

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

    def system_identifier(self, connection: Any, target: StoreTarget) -> tuple:
        """The CLUSTER's ``system_identifier``, from ``pg_control_system()``.

        Postgres mints this at ``initdb`` and it identifies the INSTALLATION,
        not the database, the connection or the address. Two DSNs reaching
        one cluster — a socket and a TCP port, a tunnel and a direct
        connection — return the same value, which is the property that makes
        it usable: it distinguishes instances without reporting a fork every
        time somebody connects by a different route.

        It also survives what a stored uuid does not. A ``pg_dump`` restored
        into a second cluster carries the store's own tables verbatim,
        ``store_uuid`` included, and reports a DIFFERENT system identifier —
        which is the 2026-08-11 case, and the one this exists to name.

        Returns UNKNOWN with the driver's own message when the role may not
        read it. ``pg_control_system()`` is superuser-only by default and
        the fleet's roles are not superusers, so this branch is the EXPECTED
        one on an ungranted cluster, not an exotic failure. The remedy —
        ``GRANT EXECUTE ON FUNCTION pg_control_system() TO <role>``, or
        ``pg_monitor`` membership — is carried in the identity error rather
        than here, where the caller would not see it.
        """
        from .._identity import UNKNOWN_SYSTEM

        try:
            found = connection.execute(
                "SELECT system_identifier::text AS sid FROM pg_control_system()"
            ).fetchone()
        except Exception as exc:
            # The failed statement aborts the surrounding transaction on
            # Postgres; roll back so an identity probe cannot poison the
            # caller's connection. Autocommit makes this a no-op, but this
            # dialect must not assume the connection it was handed is one.
            try:
                connection.rollback()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
            return (UNKNOWN_SYSTEM, f"pg_control_system() unreadable: {exc}")
        if found is None:  # pragma: no cover - the function returns one row
            return (UNKNOWN_SYSTEM, "pg_control_system() returned no row")
        value = found["sid"] if hasattr(found, "keys") else found[0]
        return (f"pg:{value}", "pg_control_system()")

    def to_db_bool(self, value: bool) -> Any:
        return bool(value)

    def from_db_bool(self, value: Any) -> bool:
        return bool(value)

# EOF
