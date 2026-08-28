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

from contextlib import contextmanager
from typing import Any, Final, Iterator, Sequence

from .._errors import DialectUnavailableError, StoreTargetError
from .._policy import FieldKind, Schema
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
            from psycopg.rows import dict_row
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
            # The codec in _codec.py addresses columns by name
            # (e.g. record["id"]), so a plain tuple from psycopg is a crash.
            # The SQLite dialect keeps the same contract via sqlite3.Row;
            # dict_row makes psycopg return a dict keyed by column name.
            connection = psycopg.connect(
                target.dsn, autocommit=True, row_factory=dict_row
            )
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
        """Existing column names from `information_schema`, in THIS schema.

        Returns zero rows for a table that does not exist, matching the
        SQLite dialect's contract — the caller reads that as "nothing to
        migrate".

        `to_regclass` is deliberately NOT used: it resolves through the whole
        search_path and would report a same-named table in another schema as
        this one. Filtering on `table_name` ALONE had that same exposure, and
        0.56.7 shipped with it — the docstring called it "the same exposure in
        principle" and left it. It is not hypothetical. `information_schema`
        lists every schema the role can see, so with a store's tables present
        in `public` and the connection pointed at a fresh schema, the probe in
        `PeerState._schema_objects_missing` reported them PRESENT, skipped
        `create_sql`, and the first read then failed:

            psycopg.errors.UndefinedTable:
                relation "comms_blocks_rows" does not exist

        `current_schema()` is the correct scope because it is where an
        unqualified `CREATE TABLE` actually lands. Asking "are the objects in
        the schema I would create them in?" makes the probe and the creator
        agree; asking "does this name exist anywhere?" does not.
        """
        escaped = table.replace("'", "''")
        return (
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{escaped}' AND table_schema = current_schema()"
        )

    def indexes_sql(self, table: str) -> str:
        """Existing index names from ``pg_indexes``, in THIS schema.

        Returns zero rows for a table that does not exist, matching
        :meth:`columns_sql`, and scoped to `current_schema()` for the same
        reason — `pg_indexes` spans every schema, so an index of the same name
        on a same-named table elsewhere would otherwise read as this one's.
        """
        escaped = table.replace("'", "''")
        return (
            f"SELECT indexname FROM pg_indexes WHERE tablename = '{escaped}' "
            "AND schemaname = current_schema()"
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
        """``pg:<cluster system_identifier>/<database>`` — instance AND database.

        Postgres mints the cluster's ``system_identifier`` at ``initdb`` and
        it identifies the INSTALLATION, not the database, the connection or
        the address. Two DSNs reaching one cluster — a socket and a TCP port,
        a tunnel and a direct connection — return the same value, which is
        the property that makes it usable: it distinguishes instances without
        reporting a fork every time somebody connects by a different route.

        It also survives what a stored uuid does not. A ``pg_dump`` restored
        into a second cluster carries the store's own tables verbatim,
        ``store_uuid`` included, and reports a DIFFERENT system identifier —
        which is the 2026-08-11 case, and the one this exists to name.

        WHY ``current_database()`` IS PART OF IT
        ----------------------------------------
        The cluster id ALONE is too coarse, and the gap is not theoretical:
        restore that same ``pg_dump`` into a second database on the SAME
        cluster and both halves report one cluster id and one ``store_uuid``
        — the uuid because it was copied, the cluster id because it genuinely
        is one installation. The pair then certifies SAME while the two
        databases accept writes independently and diverge. That is the
        original failure with a shorter blast radius, and certifying it would
        be worse than not checking, because the check would be believed.

        The database name closes it because it is engine-LOCAL: it is asked
        of the serving system rather than parsed from configuration, and
        every route into one database returns the same answer.

        WHY NOT THE RESOLVED PATH / DSN
        -------------------------------
        Proposed, and declined — it is wrong in the direction that matters.
        An address is a ROUTE, not an identity: a socket path, a TCP port and
        an SSH tunnel routinely name the SAME database, so keying on the
        address reports a fork between two views of one store every time
        anyone connects differently. A false fork alarm is worse than no
        alarm, because it trains its readers to ignore it and then the true
        one goes unread too. ``current_database()`` is the part of "where"
        that is a NAME rather than a route, which is exactly the part that
        belongs in an identity.

        Returns UNKNOWN with the driver's own message when the role may not
        read the cluster id. ``pg_control_system()`` is superuser-only by
        default and the fleet's roles are not superusers, so this branch is
        the EXPECTED one on an ungranted cluster, not an exotic failure. The
        database name is NOT substituted in that case: a database name alone
        does not distinguish two clusters that both host ``scitex``, and
        answering with the half we happen to have would certify sameness from
        a discriminator that cannot support it. The remedy — ``GRANT EXECUTE
        ON FUNCTION pg_control_system() TO <role>``, or ``pg_monitor``
        membership — is carried in the identity error rather than here, where
        the caller would not see it.
        """
        from .._identity import UNKNOWN_SYSTEM

        try:
            found = connection.execute(self.IDENTITY_SQL).fetchone()
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
        if hasattr(found, "keys"):
            value, database = found["sid"], found["db"]
        else:
            value, database = found[0], found[1]
        return (
            self.format_instance_id(value, database),
            "pg_control_system() + current_database()",
        )

    #: The statement behind :meth:`system_identifier`. Named rather than
    #: inlined so the discriminator's SHAPE is assertable without a live
    #: cluster: the defect it fixes was a MISSING COLUMN, and a test that
    #: can only run where Postgres happens to be up would not have caught it
    #: on the machine where it was written.
    IDENTITY_SQL: Final[str] = (
        "SELECT system_identifier::text AS sid, current_database() AS db "
        "FROM pg_control_system()"
    )

    @staticmethod
    def format_instance_id(system_identifier: Any, database: Any) -> str:
        """Assemble the instance half of a :class:`~.._identity.StoreIdentity`.

        Both parts are required and neither is optional-with-a-default: the
        cluster id alone cannot separate two databases on one cluster, and
        the database name alone cannot separate two clusters that both host
        ``scitex``. A discriminator built from half of this pair certifies
        sameness it cannot support.
        """
        return f"pg:{system_identifier}/{database}"

    # -- concurrency -----------------------------------------------------
    def is_unique_violation(self, exc: BaseException) -> bool:
        try:
            from psycopg.errors import UniqueViolation
        except ImportError:  # pragma: no cover - connect() already needed psycopg
            return False
        return isinstance(exc, UniqueViolation)

    @contextmanager
    def schema_lock(self, connection: Any, schema: Schema) -> Iterator[None]:
        """A session-level advisory lock keyed on the schema's oplog name.

        Held only across the DDL in ``Store.__init__`` and released in
        ``finally``, so a failing statement cannot leave it stuck. Session
        level (not transaction level) because the connection is autocommit.
        ``hashtext`` folds the name to the int4 the lock API takes; two
        schemas colliding on the hash merely serialise each other's DDL.
        """
        key = self.oplog_table(schema)
        connection.execute("SELECT pg_advisory_lock(hashtext(%s))", (key,))
        try:
            yield
        finally:
            connection.execute("SELECT pg_advisory_unlock(hashtext(%s))", (key,))

    def to_db_bool(self, value: bool) -> Any:
        return bool(value)

    def from_db_bool(self, value: Any) -> bool:
        return bool(value)

# EOF
