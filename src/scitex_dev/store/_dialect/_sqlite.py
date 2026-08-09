#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite dialect — the default backend.

Right for the common case: one host, one file, no daemon to keep alive.
The oplog makes multi-host replication work anyway, so "SQLite" does not
mean "single machine" — it means the *storage* is local and the *sharing*
is the replication layer's job.

Connection settings are chosen, not inherited:

* **WAL journal** — readers do not block the writer. Without it a single
  long read stalls every card write on the host.
* **``synchronous=NORMAL``** — with WAL this is durable across process
  crashes (only a host power-loss can lose the tail), and it is what makes
  high-frequency appends affordable.
* **``foreign_keys=ON``** — SQLite defaults this OFF per connection, which
  means constraints declared in DDL are silently unenforced.
* **``busy_timeout``** — wait for a lock instead of failing instantly, so
  two agents writing at once queue rather than raise.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Final, Sequence

from .._errors import StoreTargetError
from .._policy import FieldKind
from .._target import Backend, StoreTarget
from . import Dialect

__all__ = ["SQLiteDialect"]

_TYPES: Final[dict[FieldKind, str]] = {
    FieldKind.TEXT: "TEXT",
    FieldKind.INTEGER: "INTEGER",
    FieldKind.REAL: "REAL",
    # SQLite has no boolean type; INTEGER 0/1 is the documented idiom.
    FieldKind.BOOL: "INTEGER",
    # JSON rides in TEXT. json1 functions work on TEXT columns.
    FieldKind.JSON: "TEXT",
    FieldKind.BLOB: "BLOB",
}

#: Milliseconds to wait for a write lock before raising. Long enough to
#: absorb another agent's transaction, short enough to surface a deadlock.
BUSY_TIMEOUT_MS: Final[int] = 5_000


class SQLiteDialect(Dialect):
    """Speaks SQLite. Stateless."""

    backend = Backend.SQLITE

    def connect(self, target: StoreTarget) -> sqlite3.Connection:
        """Open the store, creating parent directories if needed."""
        path = target.path
        if path is None:  # pragma: no cover - guarded by get_dialect pairing
            raise StoreTargetError(
                f"SQLiteDialect received a non-file target {target.describe()}."
            )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StoreTargetError(
                f"Cannot create the directory for SQLite store {path}: {exc}. "
                "Check the runtime path is writable — on HPC this is often a "
                "quota (inodes, not just space) rather than a permission."
            ) from None

        connection = sqlite3.connect(str(path), isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        return connection

    def placeholder(self, index: int) -> str:
        return "?"

    def quote(self, identifier: str) -> str:
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    def column_type(self, kind: FieldKind) -> str:
        return _TYPES[kind]

    def upsert_sql(self, table: str, columns: Sequence[str], key: str) -> str:
        """``INSERT ... ON CONFLICT(key) DO UPDATE`` (SQLite >= 3.24)."""
        column_list = ", ".join(self.quote(c) for c in columns)
        updates = ", ".join(
            f"{self.quote(c)} = excluded.{self.quote(c)}"
            for c in columns
            if c != key
        )
        return (
            f"INSERT INTO {self.quote(table)} ({column_list}) "
            f"VALUES ({self.placeholders(len(columns))}) "
            f"ON CONFLICT({self.quote(key)}) DO UPDATE SET {updates}"
        )

    def to_db_bool(self, value: bool) -> Any:
        return 1 if value else 0

    def from_db_bool(self, value: Any) -> bool:
        return bool(value)

# EOF
