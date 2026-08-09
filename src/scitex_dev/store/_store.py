#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``Store`` — the write door and the read door.

Two properties are enforced here rather than documented, because both have
already cost this fleet live data.

**1. Every write is optimistically locked.** :meth:`Store.put` takes
``expected_revision`` as a REQUIRED keyword and demands the record be at
exactly that revision. A bare row-level UPDATE is not enough: two writers
who both read revision 7 and both update the same field will both succeed,
and the first change is gone with nothing raised. The lock is required
rather than offered, because an optional safety belt is worn by whoever
least needs it. See :mod:`._guards` for the contract.

**2. Nothing is deleted, ever.** There is no delete method, no DELETE
statement, and no path that removes a row. :meth:`Store.hide` sets a flag.
A test scans the generated SQL for ``DELETE``/``DROP``/``TRUNCATE`` so the
guarantee survives someone later adding a well-meaning cleanup helper.

Ordering and ownership are separate concerns
--------------------------------------------
``origin`` — the node that ACCEPTED a write — numbers the oplog and drives
replay. ``owner`` is a domain field and, under
:attr:`~._policy.WriterPolicy.MULTI_WRITER`, anyone may change it. Keying
replication on ownership would break the moment a non-owner reassigns a
record, which in the fleet's first consumer is routine.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence

from ._apply import apply_entry
from ._codec import RowCodec
from ._dialect import Dialect, get_dialect
from ._errors import RecordNotFoundError, StoreError
from ._guards import (
    ANY_REVISION,
    NEW_RECORD,
    check_owner,
    check_revision,
    record_key,
    record_key_from,
)
from ._hlc import HLC, HybridLogicalClock
from ._merge import MergeConflict
from ._oplog import OpEntry, OpKind
from ._policy import FieldRole, Schema, WriterPolicy
from ._row import Row
from ._target import StoreTarget

__all__ = ["ANY_REVISION", "NEW_RECORD", "PutResult", "Store"]

_OPLOG_COLUMNS = ("origin", "seq", "record", "op", "payload", "hlc", "actor")


@dataclass(frozen=True, slots=True)
class PutResult:
    """What a write did — one fixed shape for every write verb.

    ``created`` distinguishes an insert from an update; ``conflicts`` lists
    differences a merge rule reported rather than resolved. Named fields,
    always present, so a caller never guesses which key this call returned.
    """

    row: Row
    revision: int
    op: OpEntry
    created: bool
    conflicts: tuple[MergeConflict, ...] = ()


class Store:
    """An open store: one schema, one backend, one node identity."""

    def __init__(
        self,
        target: StoreTarget,
        schema: Schema,
        *,
        node: str,
        writer_policy: WriterPolicy,
        actor: str = "",
        clock: "HybridLogicalClock | None" = None,
        dialect: "Dialect | None" = None,
    ) -> None:
        if not node:
            raise StoreError(
                "Store requires a node id — it is the oplog's origin and the "
                "HLC's tie-breaker. Use the hostname, or the agent name where "
                "several agents share a host."
            )
        self.target = target
        self.schema = schema
        self.node = node
        self.actor = actor or node
        self.writer_policy = writer_policy
        self.clock = clock or HybridLogicalClock(node)
        self.dialect = dialect or get_dialect(target.backend)
        self.codec = RowCodec(schema, self.dialect)
        self._lock = threading.RLock()
        self._connection = self.dialect.connect(target)
        for statement in self.dialect.create_sql(schema):
            self._connection.execute(statement)

    # -- lifecycle --------------------------------------------------------
    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- write door -------------------------------------------------------
    def put(
        self,
        values: Mapping[str, Any],
        *,
        expected_revision: Any,
        owner: "str | None" = None,
        actor: "str | None" = None,
    ) -> PutResult:
        """Create or update one record under an optimistic lock.

        ``values`` carries the IDENTITY fields (which name the row) plus
        whatever is changing. Absent fields are LEFT ALONE — a put is a
        partial update, not a replacement, so two nodes editing different
        fields of one record do not clobber each other.

        ``expected_revision`` is required and three-valued:
        :data:`~._guards.NEW_RECORD`, an ``int``, or
        :data:`~._guards.ANY_REVISION`.
        """
        with self._lock:
            record = record_key(self.schema, values)
            current = self._read(record, include_hidden=True)
            check_revision(record, current, self._revision(record), expected_revision)
            if self.writer_policy is WriterPolicy.SINGLE_WRITER and current:
                check_owner(self.schema, record, current, self.actor)

            payload = {
                name: value
                for name, value in values.items()
                if self.schema.fields[name].role is not FieldRole.IDENTITY
            }
            identity = {n: values[n] for n in self.schema.identity_fields}
            entry = self._append(
                record, OpKind.UPSERT, {**identity, **payload}, actor
            )
            return self._materialise(entry, current, owner=owner)

    def hide(
        self,
        key: "Mapping[str, Any] | Sequence[Any]",
        *,
        expected_revision: Any,
        actor: "str | None" = None,
    ) -> PutResult:
        """Hide a record. The ONLY removal this store offers.

        The row, its history and every value it held stay readable through
        ``include_hidden=True`` and in the oplog. "Hidden" and "absent"
        remain distinguishable — a caller that cannot tell them apart will
        eventually treat one as the other.
        """
        return self._set_hidden(key, True, expected_revision, actor)

    def unhide(
        self,
        key: "Mapping[str, Any] | Sequence[Any]",
        *,
        expected_revision: Any,
        actor: "str | None" = None,
    ) -> PutResult:
        """Restore a hidden record to the default view."""
        return self._set_hidden(key, False, expected_revision, actor)

    def handover(
        self,
        key: "Mapping[str, Any] | Sequence[Any]",
        *,
        to_owner: str,
        expected_revision: Any,
        actor: "str | None" = None,
    ) -> PutResult:
        """Transfer a record's domain ownership.

        Under ``SINGLE_WRITER`` this is the only legal way ownership moves,
        and only the current owner may call it. Under ``MULTI_WRITER`` it is
        an ordinary change anyone may make — which is what a card
        reassignment is.
        """
        with self._lock:
            record = record_key_from(self.schema, key)
            current = self._require(record, verb="hand over")
            check_revision(record, current, self._revision(record), expected_revision)
            if self.writer_policy is WriterPolicy.SINGLE_WRITER:
                check_owner(self.schema, record, current, self.actor)
            entry = self._append(record, OpKind.HANDOVER, {"to": to_owner}, actor)
            return self._materialise(entry, current, owner=to_owner)

    # -- read door --------------------------------------------------------
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

    def revision(self, key: "Mapping[str, Any] | Sequence[Any]") -> "int | None":
        """The record's revision, or ``None`` if it does not exist."""
        with self._lock:
            record = record_key_from(self.schema, key)
            if self._read(record, include_hidden=True) is None:
                return None
            return self._revision(record)

    # -- oplog surface ----------------------------------------------------
    def changes_since(
        self, origin: str, seq: int, *, limit: int = 1000
    ) -> list[OpEntry]:
        """Ops from ``origin`` after ``seq``, ordered and contiguous.

        What a peer calls to pull. Returns a prefix starting at ``seq + 1``;
        :func:`~._replication.replay` verifies that before applying any of
        it.
        """
        with self._lock:
            table = self.dialect.quote(self.dialect.oplog_table(self.schema))
            sql = (
                f"SELECT * FROM {table} WHERE "
                f"{self.dialect.quote('origin')} = {self.dialect.placeholder(0)} "
                f"AND {self.dialect.quote('seq')} > {self.dialect.placeholder(1)} "
                f"ORDER BY {self.dialect.quote('seq')} ASC LIMIT {int(limit)}"
            )
            found = self._connection.execute(sql, (origin, seq)).fetchall()
            return [OpEntry.from_row(record) for record in found]

    def origins(self) -> dict[str, int]:
        """Every origin in the log, mapped to its highest sequence."""
        with self._lock:
            table = self.dialect.quote(self.dialect.oplog_table(self.schema))
            sql = (
                f"SELECT {self.dialect.quote('origin')} AS origin, "
                f"MAX({self.dialect.quote('seq')}) AS max_seq FROM {table} "
                f"GROUP BY {self.dialect.quote('origin')}"
            )
            return {
                record["origin"]: int(record["max_seq"])
                for record in self._connection.execute(sql).fetchall()
            }

    def cursor(self, source: str) -> int:
        """The last sequence applied from ``source``; 0 when never applied."""
        with self._lock:
            table = self.dialect.quote(self.dialect.cursor_table(self.schema))
            sql = (
                f"SELECT {self.dialect.quote('seq')} AS seq FROM {table} "
                f"WHERE {self.dialect.quote('source')} = "
                f"{self.dialect.placeholder(0)}"
            )
            found = self._connection.execute(sql, (source,)).fetchone()
            return int(found["seq"]) if found is not None else 0

    def set_cursor(self, source: str, seq: int) -> None:
        """Advance the replay cursor. Never moves it backwards."""
        with self._lock:
            existing = self.cursor(source)
            if seq < existing:
                raise StoreError(
                    f"Refusing to move the replay cursor for {source!r} "
                    f"backwards from {existing} to {seq}. Rewinding re-applies "
                    "ops already applied, dragging field timestamps backwards. "
                    "For a genuine re-sync, rebuild from the log instead."
                )
            table = self.dialect.cursor_table(self.schema)
            sql = self.dialect.upsert_sql(table, ["source", "seq"], "source")
            self._connection.execute(sql, (source, seq))

    def next_seq(self) -> int:
        """The sequence this node's next op will carry."""
        with self._lock:
            return self.origins().get(self.node, 0) + 1

    def apply_remote(self, entry: OpEntry) -> PutResult:
        """Apply one op that arrived from a peer.

        Shares :func:`~._apply.apply_entry` with the local write path — the
        same fold, so a replayed op and a locally-written one produce
        identical state. Called by :func:`~._replication.replay`, which is
        where the contiguity assertion lives; calling this directly skips
        that check.
        """
        with self._lock:
            self.clock.observe(entry.hlc)
            self._store_op(entry)
            current = self._read(entry.record, include_hidden=True)
            return self._materialise(entry, current, persist_op=False)

    # -- internals --------------------------------------------------------
    def _append(
        self,
        record: str,
        op: OpKind,
        payload: Mapping[str, Any],
        actor: "str | None",
    ) -> OpEntry:
        entry = OpEntry(
            origin=self.node,
            seq=self.next_seq(),
            record=record,
            op=op,
            payload=dict(payload),
            hlc=self.clock.now(),
            actor=actor or self.actor,
        )
        self._store_op(entry)
        return entry

    def _store_op(self, entry: OpEntry) -> None:
        table = self.dialect.quote(self.dialect.oplog_table(self.schema))
        names = ", ".join(self.dialect.quote(c) for c in _OPLOG_COLUMNS)
        sql = (
            f"INSERT INTO {table} ({names}) "
            f"VALUES ({self.dialect.placeholders(len(_OPLOG_COLUMNS))})"
        )
        self._connection.execute(
            sql,
            (
                entry.origin,
                entry.seq,
                entry.record,
                entry.op.value,
                entry.payload_json(),
                entry.hlc.encode(),
                entry.actor,
            ),
        )

    def _materialise(
        self,
        entry: OpEntry,
        current: "Row | None",
        *,
        owner: "str | None" = None,
        persist_op: bool = True,
    ) -> PutResult:
        result = apply_entry(
            self.schema,
            entry,
            current,
            owner=owner,
            default_owner=entry.actor or self.node,
        )
        revision = (self._revision(entry.record) + 1) if current is not None else 1
        table = self.dialect.rows_table(self.schema)
        columns = self.codec.row_columns()
        sql = self.dialect.upsert_sql(table, columns, "_record")
        self._connection.execute(
            sql, self.codec.row_payload(entry.record, result.row, revision)
        )
        return PutResult(
            row=result.row,
            revision=revision,
            op=entry,
            created=current is None,
            conflicts=tuple(result.conflicts),
        )

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

    def _set_hidden(
        self,
        key: "Mapping[str, Any] | Sequence[Any]",
        hidden: bool,
        expected_revision: Any,
        actor: "str | None",
    ) -> PutResult:
        with self._lock:
            record = record_key_from(self.schema, key)
            current = self._require(record, verb="hide" if hidden else "unhide")
            check_revision(record, current, self._revision(record), expected_revision)
            if self.writer_policy is WriterPolicy.SINGLE_WRITER:
                check_owner(self.schema, record, current, self.actor)
            op = OpKind.HIDE if hidden else OpKind.UNHIDE
            entry = self._append(record, op, {}, actor)
            return self._materialise(entry, current)

    def __iter__(self) -> Iterator[Row]:
        return iter(self.rows())

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"Store(schema={self.schema.name!r}, node={self.node!r}, "
            f"policy={self.writer_policy.value}, "
            f"target={self.target.describe()})"
        )

# EOF
