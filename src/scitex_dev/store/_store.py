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
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence

from ._apply import apply_entry
from ._codec import RowCodec
from ._dialect import Dialect, get_dialect
from ._errors import SeqAllocationError, StoreError
from ._guards import (
    ANY_REVISION,
    NEW_RECORD,
    check_owner,
    check_revision,
    record_key,
    record_key_from,
)
from ._hlc import HLC, HybridLogicalClock
from ._identity_state import IdentityState
from ._merge import MergeConflict
from ._oplog import OpEntry, OpKind
from ._peer_state import PeerState
from ._policy import FieldRole, Schema, WriterPolicy
from ._read_door import ReadDoor
from ._row import Row
from ._target import StoreTarget

__all__ = ["ANY_REVISION", "NEW_RECORD", "PutResult", "Store"]

# How many times _append re-reads MAX(seq) after losing the (origin, seq)
# race before giving up. Each loss means another writer on this node won an
# insert in the window between our read and ours, so the next read sees a
# higher MAX; a burst of ~14 agents settles in a handful of rounds.
_SEQ_ALLOCATION_ATTEMPTS = 32

_OPLOG_COLUMNS = (
    "origin",
    "seq",
    "record",
    "op",
    "payload",
    "hlc",
    "actor",
    "fence",
)


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


class Store(PeerState, IdentityState, ReadDoor):
    """An open store: one schema, one backend, one node identity.

    Two identities, and they answer different questions. ``node`` is who is
    WRITING — the oplog's origin and the HLC's tie-breaker. :attr:`identity`
    (from :class:`~._identity_state.IdentityState`) is which STORE this is —
    its lineage and the instance serving it. Several nodes share one store's
    identity; one node reaching two stores is the 2026-08-11 failure.
    """

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
        self._batch_depth = 0
        self._connection = self.dialect.connect(target)
        # Under the dialect's schema lock: CREATE TABLE IF NOT EXISTS is not
        # concurrency-safe on Postgres, and neither is the additive ALTER —
        # see Dialect.schema_lock. Eight agents constructing a Store for one
        # schema at once is a normal relaunch, not an edge case.
        with self.dialect.schema_lock(self._connection, schema):
            # Only when something is actually absent: the DDL is idempotent by
            # IF NOT EXISTS but NOT by privilege — PostgreSQL demands table
            # ownership before that clause short-circuits, which locked every
            # non-owning role out of stores it had full DML on. See
            # PeerState._schema_objects_missing.
            if self._schema_objects_missing(schema):
                for statement in self.dialect.create_sql(schema):
                    self._connection.execute(statement)
            self._apply_additive_migrations(schema)

    # -- lifecycle --------------------------------------------------------
    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self._connection.close()

    @contextmanager
    def batch(self) -> "Iterator[Store]":
        """Group many writes into ONE transaction instead of one each.

        Both dialects connect in autocommit, which is the right default for
        interactive single writes and the wrong one for bulk work: a single
        logical op here costs three statements (oplog insert, row upsert,
        cursor advance) and therefore three commits, each a durable write.

        Measured twice, because one large batch and many small ones could
        plausibly have had opposite signs. They do not.

            3,712-op adoption      18.59 -> 2.06 ms/op      9.0x
            60 replays of 5 ops     8.99 -> 1.04 ms/op      8.65x

        The second run alternated the two variants three times, because the
        host was under load 9.3 and a sequential A-then-B comparison had
        already produced a misleading result in the opposite direction. Run
        medians were 1.69/4.88/2.70 against 0.31/1.32/0.24 — noisy, but with
        no overlap between the two sets, which is what licenses the claim.

        READ THE RATIO AS DIRECTIONAL, NOT PORTABLE. Both were taken on a
        FUSE-backed filesystem where an fsync is dearer than on local disk,
        so this is near a best case. What generalises is the SHAPE: cost is
        per COMMIT rather than per row, so it does not shrink as the data
        does, and it is paid again on every replay during catch-up.

        Nesting is a no-op rather than an error: `install_genesis` batches and
        calls `replay`, which batches too. A second BEGIN would raise, and
        making the caller track whether someone above already opened one is
        exactly the bookkeeping this is meant to remove.

        On any exception the transaction is rolled back, so a failed batch
        applies NOTHING. See :func:`~._replication.replay` for what that
        means for cursor resumability — it is a deliberate change, and a
        safer one.
        """
        with self._lock:
            if self._batch_depth:
                self._batch_depth += 1
                try:
                    yield self
                finally:
                    self._batch_depth -= 1
                return

            self._connection.execute("BEGIN")
            self._batch_depth = 1
            try:
                yield self
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            else:
                self._connection.execute("COMMIT")
            finally:
                self._batch_depth = 0

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
    # `get`, `is_hidden`, `rows`, `revision`, `search`, `count`, `tally` and
    # the single-row SELECTs they share live in `._read_door.ReadDoor`, a
    # mixin of this class. Reading and writing change for different reasons
    # — a new filter has nothing to do with optimistic locking — and peer
    # state and store identity were already lifted out for that reason.

    # -- oplog surface -----------------------------------------------------
    # `changes_since`, `origins`, `next_seq`, `cursor`/`set_cursor` and
    # `fence`/`set_fence` live in `_peer_state.PeerState`. They are all
    # "what this node knows about OTHER nodes" and touch only the oplog and
    # cursor tables, never the rows table's merge policies.

    def apply_remote(self, entry: OpEntry) -> PutResult:
        """Apply one op that arrived from a peer.

        Shares :func:`~._apply.apply_entry` with the local write path — the
        same fold, so a replayed op and a locally-written one produce
        identical state. Called by :func:`~._replication.replay`, which is
        where the contiguity assertion lives; calling this directly skips
        that check.

        ENFORCES THE WRITER POLICY, which it previously did not. Under
        ``SINGLE_WRITER`` the local path refuses a write to a record the
        actor does not own (:meth:`put`, :meth:`handover`, :meth:`hide`),
        and this path let exactly that write in through replication instead.
        A rule the front door enforces and the back door does not is not a
        rule; it is a detour.

        DELIBERATELY DOES NOT CHECK THE REVISION, and that is not the same
        omission. ``expected_revision`` is a compare-and-swap for a caller
        who READ a value and wants to write it back. A replayed op is
        history that already happened somewhere else — it has no local
        revision to have raced against, and rejecting it because the local
        row moved on would break replay precisely when both sides wrote,
        which is the only time replay matters. Concurrent edits are resolved
        by per-field HLC merge (:mod:`._merge`), which is the mechanism for
        that job. See ADR-0011.
        """
        with self._lock:
            current = self._read(entry.record, include_hidden=True)
            if self.writer_policy is WriterPolicy.SINGLE_WRITER and current:
                check_owner(
                    self.schema,
                    entry.record,
                    current,
                    entry.actor or entry.origin,
                )
            self.clock.observe(entry.hlc)
            self._store_op(entry)
            return self._materialise(entry, current, persist_op=False)

    # -- internals --------------------------------------------------------
    def _new_entry(
        self,
        record: str,
        op: OpKind,
        payload: Mapping[str, Any],
        actor: "str | None",
    ) -> OpEntry:
        return OpEntry(
            origin=self.node,
            seq=self.next_seq(),
            record=record,
            op=op,
            payload=dict(payload),
            hlc=self.clock.now(),
            actor=actor or self.actor,
            # Write under the authority we currently hold, not under none.
            # Every local op used to carry FENCE_UNKNOWN, which made fencing
            # a suicide pact: the moment any fence rose for this node, this
            # node's own ops fell below it and every peer rejected them. It
            # is 0 until somebody promotes us, so unfenced fleets behave
            # exactly as before.
            fence=self.fence(self.node),
        )

    def _append(
        self,
        record: str,
        op: OpKind,
        payload: Mapping[str, Any],
        actor: "str | None",
    ) -> OpEntry:
        # seq is allocated by reading MAX(seq) and inserting MAX + 1, and
        # ``self._lock`` guards only THIS instance — a second Store on the
        # same node (one per agent; ~14 relaunch together) can read the same
        # MAX. The (origin, seq) primary key then rejects the loser, which is
        # exactly the signal to re-read and go again: nothing was written.
        # Measured before this loop existed: 5 of 8 concurrent writers with
        # DISTINCT ids died on the PK, as a raw driver exception.
        #
        # Inside batch() the connection is mid-transaction, and on Postgres a
        # rejected INSERT aborts that transaction; a SAVEPOINT scopes the
        # failure to this one statement so the retry — and the caller's
        # batch — can continue. Outside a batch the connection is autocommit
        # and needs none (SAVEPOINT outside a transaction is itself an error).
        for _attempt in range(_SEQ_ALLOCATION_ATTEMPTS):
            entry = self._new_entry(record, op, payload, actor)
            in_batch = self._batch_depth > 0
            if in_batch:
                self._connection.execute("SAVEPOINT seq_alloc")
            try:
                self._store_op(entry)
            except Exception as exc:
                if not self.dialect.is_unique_violation(exc):
                    raise
                if in_batch:
                    self._connection.execute("ROLLBACK TO SAVEPOINT seq_alloc")
                continue
            if in_batch:
                self._connection.execute("RELEASE SAVEPOINT seq_alloc")
            return entry
        raise SeqAllocationError(
            f"Could not allocate an oplog seq for origin {self.node!r} after "
            f"{_SEQ_ALLOCATION_ATTEMPTS} attempts: every attempt lost the "
            "(origin, seq) race to another writer on this node. Nothing was "
            "written; the operation may be retried whole. Sustained loss at "
            "this rate means far more concurrent writers than a launch burst."
        )

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
                entry.fence,
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

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"Store(schema={self.schema.name!r}, node={self.node!r}, "
            f"policy={self.writer_policy.value}, "
            f"target={self.target.describe()})"
        )

# EOF
