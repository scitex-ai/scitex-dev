#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The dialect layer — one interface, two backends, no leakage.

Callers of :mod:`scitex_dev.store` never write SQL and never learn which
engine they are on. Everything a backend does differently lives behind
:class:`Dialect`: parameter style, identifier quoting, type names, upsert
syntax, and how a connection is opened.

The two backends are not peers. **SQLite is the default** — a single file
under ``runtime/``, no daemon, right for every store that lives on one
host. **Postgres is advanced** — reach for it when a store genuinely needs
concurrent writers from several hosts or does not fit one file.

Choosing Postgres when its driver is absent raises
:class:`~.._errors.DialectUnavailableError`. It does NOT quietly fall back
to SQLite: a caller that asked for a shared database and silently received
a private local file would see every write succeed and none of them reach
anyone else.

One rule is enforced here rather than documented: **no dialect emits
DELETE, DROP or TRUNCATE.** Hiding is a flag update. There is a test
asserting the generated SQL contains none of those verbs, so the rule
survives someone adding a "cleanup" helper later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
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
            f"PRIMARY KEY ({self.quote('origin')}, {self.quote('seq')}))",
            f"CREATE TABLE IF NOT EXISTS {self.quote(cursor)} ("
            f"{self.quote('source')} {text} PRIMARY KEY, "
            f"{self.quote('seq')} {integer} NOT NULL)",
            f"CREATE INDEX IF NOT EXISTS {self.quote(oplog + '_record_idx')} "
            f"ON {self.quote(oplog)} ({self.quote('record')})",
            f"CREATE INDEX IF NOT EXISTS {self.quote(rows + '_hidden_idx')} "
            f"ON {self.quote(rows)} ({self.quote('_hidden')})",
        ]
        statements.extend(
            f"CREATE INDEX IF NOT EXISTS "
            f"{self.quote(f'{rows}_{name}_idx')} ON {self.quote(rows)} "
            f"({self.quote(name)})"
            for name in schema.indexed_fields
        )
        return statements

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
    if resolved is Backend.SQLITE:
        from ._sqlite import SQLiteDialect

        return SQLiteDialect()
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
