#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The dialect layer — one interface, one backend, no leakage.

Callers of :mod:`scitex_dev.store` never write SQL and never learn how the
engine is spoken to. Everything engine-specific lives behind
:class:`Dialect`: parameter style, identifier quoting, type names, upsert
syntax, and how a connection is opened.

There is ONE backend: the per-host PostgreSQL on 55432, synchronised across
hosts. The interface stays an abstraction anyway, because it is what keeps
SQL out of the callers — not because a second engine is coming.

The rule behind that is the fleet's, not a preference here (constitution
§3, operator's ruling 2026-08-14): *spec は設計書、状態は db* — design
belongs to git, state belongs to the database. If losing a file would lose
a fact nobody else holds, it is state, and state has exactly one home.

WHY THE SECOND BACKEND IS GONE AND WHAT IT COST. Until 2026-08-21 this
docstring and the sibling READMEs named a file-backed engine as the default
and Postgres as "advanced", in four places. Nothing in the code enforced
it — :func:`get_dialect` takes an explicit backend — so the sentence WAS
the mechanism: it is what a reader consults when choosing. A fleet survey
the same day counted 66 of 68 live tables in one consumer package sitting
on the wrong engine. Whoever put them there was following this file
correctly. A default stated only in prose is still a default; the fix was
to stop shipping the thing it defaulted to. ADR-0006 keeps the full record.

Running without the Postgres driver raises
:class:`~.._errors.DialectUnavailableError`. There is nothing to fall back
to, which is the point: a caller that asked for a shared database and
silently received a private local file would see every write succeed and
none of them reach anyone else.

One rule is enforced here rather than documented: **no dialect emits
DELETE, DROP or TRUNCATE.** Hiding is a flag update. There is a test
asserting the generated SQL contains none of those verbs, so the rule
survives someone adding a "cleanup" helper later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager, nullcontext
from typing import Any, Final, Iterable, Sequence

from .._errors import DialectUnavailableError
from .._policy import FieldKind, Schema
from .._target import Backend, StoreTarget

__all__ = [
    "CURSOR_COLUMNS",
    "Dialect",
    "OPLOG_COLUMNS",
    "SYSTEM_COLUMNS",
    "get_dialect",
]

#: Bookkeeping columns the rows table always carries, in fixed order.
#: ``_owner`` is the record's domain owner; ``_origin``/``_seq`` record
#: which node's op last touched it. They are different things and both are
#: needed — see :class:`~.._policy.WriterPolicy`.
SYSTEM_COLUMNS: Final[tuple[str, ...]] = (
    "_record",
    "_owner",
    "_origin",
    "_seq",
    "_revision",
    "_hlc",
    "_hidden",
    "_field_hlc",
)

#: The append-only log's columns. ``(origin, seq)`` is its primary key and
#: ``seq`` is gapless per origin — that is what makes directed replay
#: verifiable. ``actor`` is domain information and never affects ordering.
OPLOG_COLUMNS: Final[tuple[str, ...]] = (
    "origin",
    "seq",
    "record",
    "op",
    "payload",
    "hlc",
    "actor",
)

#: Per-source replay cursors: the last sequence number applied from a peer.
CURSOR_COLUMNS: Final[tuple[str, ...]] = ("source", "seq")

#: The store's own identity row(s): a key/value pair table holding the
#: LINEAGE half of :class:`~.._identity.StoreIdentity`. The INSTANCE half is
#: deliberately NOT stored here — a value kept inside the database is copied
#: with the database, which is precisely why a ``store_uuid`` alone cannot
#: detect a fork of itself.
IDENTITY_COLUMNS: Final[tuple[str, ...]] = ("key", "value")

#: The row key under which the lineage uuid lives.
STORE_UUID_KEY: Final[str] = "store_uuid"


class Dialect(ABC):
    """What one backend does differently. Stateless; safe to share."""

    #: Value of :class:`~.._target.Backend` this dialect serves.
    backend: Backend

    # -- connection -------------------------------------------------------
    @abstractmethod
    def connect(self, target: StoreTarget) -> Any:
        """Open a DB-API connection, creating the store if it is absent."""

    # -- syntax -----------------------------------------------------------
    @abstractmethod
    def placeholder(self, index: int) -> str:
        """The bind-parameter marker for the ``index``-th value (0-based)."""

    @abstractmethod
    def quote(self, identifier: str) -> str:
        """Quote a table or column name."""

    @abstractmethod
    def column_type(self, kind: FieldKind) -> str:
        """The backend's column type for a :class:`~.._policy.FieldKind`."""

    @abstractmethod
    def upsert_sql(self, table: str, columns: Sequence[str], key: str) -> str:
        """An INSERT that overwrites on primary-key conflict."""

    # -- query fragments --------------------------------------------------
    #
    # Concrete-and-raising rather than abstract, on purpose. A dialect can
    # arrive through the federation entry point (see `.federation`), and
    # adding an abstract method would stop every such plugin from importing
    # — a hard failure at construction for a capability it may never use.
    # Refusing at the moment the capability is ASKED for names the missing
    # piece and leaves everything else working.

    def text_vector_sql(self, schema: Schema) -> str:
        """The searchable-text expression over ``schema.text_search``.

        ONE method builds it, and both the index and the query read from
        this one. They must be character-identical: an expression index
        that differs from its query by a space is never used, the planner
        reports nothing, and the only symptom is that search got slow.
        """
        raise DialectUnavailableError(
            f"The {self.backend.value} dialect states no full-text "
            "expression, so a schema cannot be searched through it."
        )

    def text_match_sql(self, schema: Schema, placeholder: str) -> str:
        """A boolean expression: does this row match the bound query text?"""
        raise DialectUnavailableError(
            f"The {self.backend.value} dialect states no full-text match "
            "syntax, so Query.matching(...) cannot be compiled for it."
        )

    def json_contains_sql(self, column: str, placeholder: str) -> str:
        """A boolean expression: does this JSON column contain the value?"""
        raise DialectUnavailableError(
            f"The {self.backend.value} dialect states no JSON containment "
            "syntax, so contains(...) cannot be compiled for it."
        )

    def text_index_specs(self, schema: Schema) -> list[tuple[str, str, str]]:
        """``(index, table, ddl)`` for every full-text index to build.

        One tuple carries both the NAME the existence probe looks for and
        the STATEMENT that creates it, so the two cannot name different
        things — the failure mode :meth:`index_specs` documents, in the one
        place where the statement is not a uniform ``CREATE INDEX``.
        """
        return []

    def insert_ignore_sql(
        self, table: str, columns: Sequence[str], key: str
    ) -> str:
        """An INSERT that does NOTHING on primary-key conflict.

        Both backends spell this the same way, so it is concrete here rather
        than abstract. It exists for write-once facts — the store's lineage
        uuid — where an upsert would be actively wrong: two processes
        opening a fresh store at the same moment would each overwrite the
        other and walk away believing different lineages for one database.
        """
        column_list = ", ".join(self.quote(c) for c in columns)
        return (
            f"INSERT INTO {self.quote(table)} ({column_list}) "
            f"VALUES ({self.placeholders(len(columns))}) "
            f"ON CONFLICT ({self.quote(key)}) DO NOTHING"
        )

    # -- shared DDL -------------------------------------------------------
    def placeholders(self, count: int) -> str:
        """A comma-separated placeholder list for ``count`` values."""
        return ", ".join(self.placeholder(i) for i in range(count))

    def rows_table(self, schema: Schema) -> str:
        """Name of the materialised current-state table."""
        return f"{schema.name}_rows"

    def oplog_table(self, schema: Schema) -> str:
        """Name of the append-only operation log."""
        return f"{schema.name}_oplog"

    def cursor_table(self, schema: Schema) -> str:
        """Name of the per-source replay-cursor table."""
        return f"{schema.name}_cursor"

    def identity_table(self, schema: Schema) -> str:
        """Name of the store's own identity key/value table."""
        return f"{schema.name}_identity"

    # -- instance identity -------------------------------------------------
    def system_identifier(self, connection: Any, target: StoreTarget) -> tuple:
        """``(identifier, source)`` naming the INSTANCE serving ``connection``.

        The contract, and it is the whole reason this is a dialect method
        rather than a stored column: **the answer must come from the serving
        system, not from the store's own rows.** Anything read back out of
        the database was copied along with the database, so it identifies
        the ancestor equally well for every fork — which is exactly the
        failure :mod:`~.._identity` exists to end.

        Returns :data:`~.._identity.UNKNOWN_SYSTEM` plus a human-readable
        reason when the system will not say. It never fabricates a
        discriminator and never falls back to the connection string: an
        address is a route, not an identity, and a socket path and a TCP
        port routinely name one instance. Inventing a difference there would
        report a fork between two views of one store, every time.
        """
        from .._identity import UNKNOWN_SYSTEM

        return (UNKNOWN_SYSTEM, f"{self.backend.value} dialect states none")

    # -- additive migration -----------------------------------------------
    #
    # `create_sql` uses CREATE TABLE IF NOT EXISTS, which is correct for a
    # store that does not exist yet and INERT for one that does. So a column
    # added to a table definition reaches NEW stores only; every existing
    # store keeps the old shape, and the first INSERT naming the new column
    # fails there. A schema change that works on a fresh checkout and breaks
    # every deployed store is the worst shape available, because it passes
    # every test written against a temp directory.
    #
    # These two methods close that gap for the ADDITIVE case, which is the
    # only case this store needs: a new nullable/defaulted column. Dropping
    # or retyping a column is deliberately NOT supported — it is destructive
    # and belongs in a reviewed one-off, not in a path that runs on every
    # open.

    @abstractmethod
    def columns_sql(self, table: str) -> str:
        """A SELECT returning one row per existing column of ``table``.

        The first column of each row must be the column NAME. Used to decide
        whether an additive migration is needed, so it must not raise on a
        table that does not exist — return no rows instead.
        """

    def add_column_sql(self, table: str, column: str, coltype: str, default: str) -> str:
        """DDL adding one column. Only ever called when it is absent.

        No ``IF NOT EXISTS``: the caller has already established absence by
        reading :meth:`columns_sql`, and a silent no-op here would hide a
        disagreement between that read and reality rather than surface it.
        """
        return (
            f"ALTER TABLE {self.quote(table)} ADD COLUMN "
            f"{self.quote(column)} {coltype} NOT NULL DEFAULT {default}"
        )

    def additive_columns(self, schema: Schema) -> list[tuple[str, str, str, str]]:
        """``(table, column, type, default)`` for every column added since v1.

        Each entry is applied only where missing. Append here when adding a
        column to :meth:`create_sql`; the two must agree, or a fresh store and
        a migrated one end up with different shapes — which is the divergence
        this whole mechanism exists to prevent.
        """
        integer = self.column_type(FieldKind.INTEGER)
        return [
            # The oplog fence: the authority an op was written under.
            # See _errors.SupersededFenceError.
            (self.oplog_table(schema), "fence", integer, "0"),
            # The highest fence accepted from a peer, alongside its cursor —
            # both are "what we know about that peer", so they share a table.
            (self.cursor_table(schema), "fence", integer, "0"),
        ]

    def create_sql(self, schema: Schema) -> list[str]:
        """Every DDL statement needed for ``schema``, in execution order.

        Contains no DELETE / DROP / TRUNCATE, by construction and by test.
        """
        text = self.column_type(FieldKind.TEXT)
        integer = self.column_type(FieldKind.INTEGER)
        boolean = self.column_type(FieldKind.BOOL)

        user_columns = [
            f"{self.quote(name)} {self.column_type(policy.kind)}"
            for name, policy in schema.fields.items()
        ]
        rows = self.rows_table(schema)
        oplog = self.oplog_table(schema)
        cursor = self.cursor_table(schema)

        statements = [
            f"CREATE TABLE IF NOT EXISTS {self.quote(rows)} ("
            f"{self.quote('_record')} {text} PRIMARY KEY, "
            f"{self.quote('_owner')} {text} NOT NULL, "
            f"{self.quote('_origin')} {text} NOT NULL, "
            f"{self.quote('_seq')} {integer}, "
            f"{self.quote('_revision')} {integer} NOT NULL, "
            f"{self.quote('_hlc')} {text} NOT NULL, "
            f"{self.quote('_hidden')} {boolean} NOT NULL, "
            f"{self.quote('_field_hlc')} {text} NOT NULL"
            + (", " + ", ".join(user_columns) if user_columns else "")
            + ")",
            f"CREATE TABLE IF NOT EXISTS {self.quote(oplog)} ("
            f"{self.quote('origin')} {text} NOT NULL, "
            f"{self.quote('seq')} {integer} NOT NULL, "
            f"{self.quote('record')} {text} NOT NULL, "
            f"{self.quote('op')} {text} NOT NULL, "
            f"{self.quote('payload')} {text} NOT NULL, "
            f"{self.quote('hlc')} {text} NOT NULL, "
            f"{self.quote('actor')} {text} NOT NULL, "
            f"{self.quote('fence')} {integer} NOT NULL DEFAULT 0, "
            f"PRIMARY KEY ({self.quote('origin')}, {self.quote('seq')}))",
            f"CREATE TABLE IF NOT EXISTS {self.quote(cursor)} ("
            f"{self.quote('source')} {text} PRIMARY KEY, "
            f"{self.quote('seq')} {integer} NOT NULL, "
            f"{self.quote('fence')} {integer} NOT NULL DEFAULT 0)",
            # The lineage half of the store's identity. A separate table
            # rather than a column on an existing one: it is per-STORE, not
            # per-row and not per-peer, and hanging a store-wide fact off a
            # row table makes it ambiguous which row carries the real answer.
            f"CREATE TABLE IF NOT EXISTS {self.quote(self.identity_table(schema))} ("
            f"{self.quote('key')} {text} PRIMARY KEY, "
            f"{self.quote('value')} {text} NOT NULL)",
        ]
        statements.extend(
            f"CREATE INDEX IF NOT EXISTS {self.quote(index)} "
            f"ON {self.quote(table)} ({self.quote(column)})"
            for index, table, column in self.index_specs(schema)
        )
        statements.extend(ddl for _index, _table, ddl in self.text_index_specs(schema))
        return statements

    def index_specs(self, schema: Schema) -> list[tuple[str, str, str]]:
        """``(index, table, column)`` for every index ``create_sql`` builds.

        Factored out so the CREATE and the existence probe in
        ``Store.__init__`` read from ONE list. The same reasoning as
        :meth:`additive_columns`: two places that must agree about the shape
        of a store will eventually disagree if each keeps its own copy, and
        the failure then looks like a permissions bug rather than a drift.
        """
        rows = self.rows_table(schema)
        oplog = self.oplog_table(schema)
        specs = [
            (oplog + "_record_idx", oplog, "record"),
            (rows + "_hidden_idx", rows, "_hidden"),
        ]
        specs.extend((f"{rows}_{name}_idx", rows, name) for name in schema.indexed_fields)
        return specs

    def schema_tables(self, schema: Schema) -> list[str]:
        """Every table ``create_sql`` builds, for the same reason as above."""
        return [
            self.rows_table(schema),
            self.oplog_table(schema),
            self.cursor_table(schema),
            self.identity_table(schema),
        ]

    @abstractmethod
    def indexes_sql(self, table: str) -> str:
        """A SELECT returning one row per existing INDEX on ``table``.

        The first column of each row must be the index NAME. Like
        :meth:`columns_sql` it must not raise on a table that does not
        exist — return no rows instead.
        """

    # -- concurrency -----------------------------------------------------
    #
    # Two Store instances on one host are the NORMAL case (one per agent; the
    # operator relaunches ~14 at once), and they share nothing in Python —
    # ``Store._lock`` is per instance. Whatever must be atomic across them has
    # to be atomic in the DATABASE. These two hooks are how the store asks the
    # dialect for that. The base-class answers below are the conservative
    # ones — classify nothing, lock nothing — so a dialect that does not
    # override them re-raises rather than retrying blind.

    def is_unique_violation(self, exc: BaseException) -> bool:
        """Whether ``exc`` is the driver's unique-constraint rejection.

        The store retries an oplog append when this is True: the
        ``(origin, seq)`` primary key rejecting a write means another writer
        on the same node took that seq between our MAX read and our INSERT —
        a race to re-read, not a fault. Anything else is re-raised untouched.
        """
        return False

    def schema_lock(
        self, connection: Any, schema: Schema
    ) -> AbstractContextManager[None]:
        """Serialise ``create_sql`` across concurrent Store constructors.

        ``CREATE TABLE IF NOT EXISTS`` is NOT concurrency-safe on Postgres:
        two sessions that both see the table absent both create it, and the
        second collides on the table's implicit row TYPE in ``pg_type``
        before the name check ever runs (measured 2026-08-24: 7 of 8
        concurrent constructors failed on ``pg_type_typname_nsp_index``).
        The additive ``ALTER TABLE ADD COLUMN`` migration races the same way.
        The base implementation is a no-op; the Postgres dialect overrides it.
        """
        return nullcontext()

    def to_db_bool(self, value: bool) -> Any:
        """Render a Python bool for this backend."""
        return 1 if value else 0

    def from_db_bool(self, value: Any) -> bool:
        """Read this backend's boolean back into Python."""
        return bool(value)


def get_dialect(backend: "Backend | str") -> Dialect:
    """Return the dialect for ``backend``.

    Raises :class:`~.._errors.DialectUnavailableError` when the backend is
    known but its driver is not installed — never a silent substitution.
    """
    resolved = Backend(backend) if not isinstance(backend, Backend) else backend
    if resolved is Backend.POSTGRES:
        from ._postgres import PostgresDialect

        return PostgresDialect()
    raise DialectUnavailableError(  # pragma: no cover - Backend() guards this
        f"No dialect for backend {resolved!r}. Known: "
        f"{[b.value for b in Backend]}."
    )


def iter_dialects() -> Iterable[Backend]:
    """The backends this layer can name (not necessarily installed)."""
    return tuple(Backend)

# EOF
