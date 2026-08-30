#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``ReadDoor`` — every way of getting records back out of a store.

A mixin, like :class:`~._peer_state.PeerState` and
:class:`~._identity_state.IdentityState` beside it, folded into
:class:`~._store.Store`. It owns no state: the connection, dialect, codec,
schema and lock are the store's, and this module only decides what to ask
them for.

WHY IT IS A FILE OF ITS OWN. Reading and writing change for different
reasons — a new sort key or filter has nothing to do with optimistic
locking or oplog sequencing — and the two were interleaved in one module
that had already outgrown the repository's size limit. Peer state and store
identity had already been lifted out for the same reason; the read door was
the piece left behind.

THE THREE QUESTIONS, and they are genuinely three:

* :meth:`get` / :meth:`is_hidden` / :meth:`revision` — about ONE key.
* :meth:`rows` — everything, unfiltered.
* :meth:`search` / :meth:`count` / :meth:`tally` — a CRITERION.

Until the third group existed there was nothing between "one row" and "all
of them", so a consumer with a filter had to fetch the table and narrow it
in Python. That is the point at which a package stops using this store and
starts building a private index of its own — which is exactly what
scitex-dataset had done, and what removing it required this to exist.

HIDDEN ROWS ARE EXCLUDED BY DEFAULT, EVERYWHERE HERE. Nothing is ever
deleted (see :class:`~._store.Store`), so the default view is the only
thing standing between a caller and every record the store has ever held.
Each verb takes an explicit opt-in instead — ``include_hidden`` on the
key-and-table verbs, :meth:`~._query.Query.with_hidden` on a query.
"""

from __future__ import annotations

from typing import Any, Iterator, Mapping, Sequence

from ._errors import RecordNotFoundError
from ._guards import record_key_from
from ._query import Query
from ._query_sql import compile_count, compile_select, compile_tally
from ._row import Row

__all__ = ["ReadDoor"]


class ReadDoor:
    """The read half of :class:`~._store.Store`. Not useful on its own."""

    # -- by key -----------------------------------------------------------
    def get(
        self,
        key: "Mapping[str, Any] | Sequence[Any]",
        *,
        include_hidden: bool = False,
    ) -> "Row | None":
        """One record, or ``None`` if absent from the chosen view.

        With ``include_hidden=False`` a hidden row reads as ``None``. Use
        :meth:`is_hidden` when the difference matters.
        """
        with self._lock:
            return self._read(record_key_from(self.schema, key), include_hidden)

    def is_hidden(self, key: "Mapping[str, Any] | Sequence[Any]") -> "bool | None":
        """Three-valued: ``True`` hidden, ``False`` visible, ``None`` absent."""
        with self._lock:
            row = self._read(record_key_from(self.schema, key), include_hidden=True)
            return None if row is None else row.hidden

    def revision(self, key: "Mapping[str, Any] | Sequence[Any]") -> "int | None":
        """The record's revision, or ``None`` if it does not exist."""
        with self._lock:
            record = record_key_from(self.schema, key)
            if self._read(record, include_hidden=True) is None:
                return None
            return self._revision(record)

    # -- everything -------------------------------------------------------
    def rows(self, *, include_hidden: bool = False) -> list[Row]:
        """Every record in the chosen view."""
        with self._lock:
            table = self.dialect.quote(self.dialect.rows_table(self.schema))
            if include_hidden:
                found = self._connection.execute(f"SELECT * FROM {table}").fetchall()
            else:
                sql = (
                    f"SELECT * FROM {table} WHERE "
                    f"{self.dialect.quote('_hidden')} = {self.dialect.placeholder(0)}"
                )
                found = self._connection.execute(
                    sql, (self.dialect.to_db_bool(False),)
                ).fetchall()
            return [self.codec.row_from_db(record) for record in found]

    def __iter__(self) -> Iterator[Row]:
        return iter(self.rows())

    # -- by criterion -----------------------------------------------------
    def search(self, query: "Query | None" = None) -> list[Row]:
        """Records matching ``query``, ordered and paged by it.

        The middle of the read door. A query with no criteria is
        :meth:`rows` with a deterministic order; one with a text criterion
        needs the schema to declare ``text_search`` fields, and says so
        rather than returning nothing if it does not.
        """
        resolved = query if query is not None else Query()
        with self._lock:
            statement = compile_select(
                resolved,
                self.schema,
                self.dialect,
                self.codec,
                self.dialect.rows_table(self.schema),
            )
            found = self._connection.execute(
                statement.sql, statement.params
            ).fetchall()
            return [self.codec.row_from_db(record) for record in found]

    def count(self, query: "Query | None" = None) -> int:
        """How many records match ``query``. Its order and paging are ignored.

        Ignoring the query's own LIMIT is the point, not an omission:
        ``len(store.search(q))`` would cap the answer at the page size and
        report "50 results" for a set of nine thousand. It also avoids
        transferring every matching row to arrive at a number.
        """
        resolved = query if query is not None else Query()
        with self._lock:
            statement = compile_count(
                resolved,
                self.schema,
                self.dialect,
                self.codec,
                self.dialect.rows_table(self.schema),
            )
            found = self._connection.execute(
                statement.sql, statement.params
            ).fetchone()
            return int(found["n"]) if found is not None else 0

    def tally(self, group: str, query: "Query | None" = None) -> "dict[Any, int]":
        """Matching records per distinct value of ``group``.

        The "how many of each" every status board and index-health report
        asks for. In SQL it is one grouped count; over :meth:`rows` it is
        the whole table in memory, which is how a one-line summary becomes
        the most expensive call in a CLI.
        """
        resolved = query if query is not None else Query()
        with self._lock:
            statement = compile_tally(
                resolved,
                self.schema,
                self.dialect,
                self.codec,
                self.dialect.rows_table(self.schema),
                group,
            )
            found = self._connection.execute(
                statement.sql, statement.params
            ).fetchall()
            return {
                self.codec.decode_value(group, record["bucket"]): int(record["n"])
                for record in found
            }

    # -- internals --------------------------------------------------------
    #
    # The write door calls these too — `put` reads the current row before it
    # can merge onto it, and `handover` must raise on a record that is not
    # there. They live with the reads because that is what they are.

    def _revision(self, record: str) -> int:
        table = self.dialect.quote(self.dialect.rows_table(self.schema))
        sql = (
            f"SELECT {self.dialect.quote('_revision')} AS rev FROM {table} "
            f"WHERE {self.dialect.quote('_record')} = "
            f"{self.dialect.placeholder(0)}"
        )
        found = self._connection.execute(sql, (record,)).fetchone()
        return int(found["rev"]) if found is not None else 0

    def _read(self, record: str, include_hidden: bool) -> "Row | None":
        table = self.dialect.quote(self.dialect.rows_table(self.schema))
        sql = (
            f"SELECT * FROM {table} WHERE {self.dialect.quote('_record')} = "
            f"{self.dialect.placeholder(0)}"
        )
        found = self._connection.execute(sql, (record,)).fetchone()
        if found is None:
            return None
        row = self.codec.row_from_db(found)
        return None if (row.hidden and not include_hidden) else row

    def _require(self, record: str, *, verb: str) -> Row:
        row = self._read(record, include_hidden=True)
        if row is None:
            raise RecordNotFoundError(
                f"Cannot {verb} record {record!r} in store "
                f"{self.schema.name!r}: it does not exist. Nothing deleted it "
                "— this store has no delete — so check the key."
            )
        return row

# EOF
