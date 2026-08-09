#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One host's replica: its append-only log, its fences, its intents, its state.

Everything a replica needs in order to (a) accept local writes while cut
off from every peer, and (b) hand an ordered, self-describing stream of
those writes to any peer that later asks. Nothing here ever inspects a
peer's contents, because reconciliation is directed replay -- see
:mod:`._replay`.

Three pieces earn their keep only when something goes wrong, which is
exactly why they are not deferred:

* the **fence column** on every op, so a superseded writer's ops arrive
  distinguishable from a current writer's rather than as legitimate work;
* the **applied-intents ledger**, so a lost ACK cannot make a write that
  actually landed report as a refusal and send the caller round again on
  an operation that is already complete;
* the **per-origin cursor**, one monotone integer, which is the entire
  reconciliation state -- no comparison, no diff, no snapshot.
"""

from __future__ import annotations

import time

from ._oplog_dialect import (
    POSTGRES,
    OplogTarget,
    connect,
    record_apply_sql,
    record_select_sql,
    translate,
)
from ._oplog_dialect import DDL_STATEMENTS
from ._oplog_model import (
    FENCE_UNKNOWN,
    OP_DELETE,
    OP_UPSERT,
    Op,
    SingleWriterViolationError,
    SupersededFenceError,
    utc_now_iso,
)
from ._reading import (
    DEFAULT_SILENCE_THRESHOLD_S,
    Reading,
    Watermark,
    silences_from,
)

__all__ = ["OpLogStore"]

_OPLOG_INSERT = """
INSERT INTO stx_oplog
    (origin, seq, table_name, record_key, op, payload, fence, ts)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (origin, seq) DO NOTHING
"""

_OPLOG_SELECT = """
SELECT origin, seq, table_name, record_key, op, payload, fence, ts
FROM stx_oplog
WHERE origin = ? AND seq > ?
ORDER BY seq ASC
"""


class OpLogStore:
    """A single replica, identified by ``origin``, backed by a real database."""

    def __init__(
        self,
        target: OplogTarget,
        origin: str,
        *,
        silence_threshold_s: float = DEFAULT_SILENCE_THRESHOLD_S,
    ) -> None:
        if not origin:
            raise ValueError("origin must be a non-empty host identifier")
        self.target = target
        self.origin = origin
        self.silence_threshold_s = silence_threshold_s
        self._conn = connect(target)
        self._ensure_schema()

    # -- plumbing ---------------------------------------------------------

    def _exec(self, sql: str, params: tuple = ()):
        return self._conn.execute(translate(sql, self.target.dialect), params)

    def _ensure_schema(self) -> None:
        for statement in DDL_STATEMENTS:
            self._conn.execute(statement)
        self._conn.commit()
        if self.fence_for(self.origin) == FENCE_UNKNOWN:
            self.set_fence(self.origin, 1)
        self.touch(self.origin)

    def close(self) -> None:
        self._conn.close()

    def columns_of(self, table_name: str) -> tuple:
        """Column names as the LIVE database reports them.

        Used to prove structural claims (``fence`` is a column of the
        oplog) against the engine rather than against the source text.
        """
        if self.target.dialect == POSTGRES:
            schema = self.target.namespace or "public"
            rows = self._exec(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = ? AND table_schema = ? "
                "ORDER BY ordinal_position",
                (table_name, schema),
            ).fetchall()
            return tuple(row[0] for row in rows)
        rows = self._conn.execute(
            "PRAGMA table_info({0})".format(table_name)
        ).fetchall()
        return tuple(row[1] for row in rows)

    # -- fences -----------------------------------------------------------

    def fence_for(self, origin: str) -> int:
        row = self._exec(
            "SELECT fence FROM stx_fence WHERE origin = ?", (origin,)
        ).fetchone()
        return FENCE_UNKNOWN if row is None else int(row[0])

    def set_fence(self, origin: str, fence: int) -> None:
        self._exec(
            "INSERT INTO stx_fence (origin, fence) VALUES (?, ?) "
            "ON CONFLICT (origin) DO UPDATE SET fence = excluded.fence",
            (origin, int(fence)),
        )
        self._conn.commit()

    def bump_fence(self) -> int:
        """Take over as writer for this origin; ops below the new fence die."""
        fence = self.fence_for(self.origin) + 1
        self.set_fence(self.origin, fence)
        return fence

    # -- cursors ----------------------------------------------------------

    def cursor_for(self, origin: str) -> int:
        row = self._exec(
            "SELECT applied_seq FROM stx_cursor WHERE origin = ?", (origin,)
        ).fetchone()
        return 0 if row is None else int(row[0])

    def set_cursor(self, origin: str, applied_seq: int, *, heard_at: str = "") -> None:
        self._exec(
            "INSERT INTO stx_cursor (origin, applied_seq, last_heard_at) "
            "VALUES (?, ?, ?) ON CONFLICT (origin) DO UPDATE SET "
            "applied_seq = excluded.applied_seq, "
            "last_heard_at = excluded.last_heard_at",
            (origin, int(applied_seq), heard_at or utc_now_iso()),
        )
        self._conn.commit()

    def touch(self, origin: str, *, heard_at: str = "") -> None:
        """Record contact with ``origin`` WITHOUT moving its cursor."""
        self.set_cursor(origin, self.cursor_for(origin), heard_at=heard_at)

    def known_origins(self) -> tuple:
        rows = self._exec(
            "SELECT origin FROM stx_cursor ORDER BY origin", ()
        ).fetchall()
        return tuple(row[0] for row in rows)

    def watermark(self) -> Watermark:
        rows = self._exec(
            "SELECT origin, applied_seq FROM stx_cursor ORDER BY origin", ()
        ).fetchall()
        return Watermark(tuple((row[0], int(row[1])) for row in rows))

    def heard_pairs(self) -> tuple:
        """``(origin, last_heard_at)`` for every PEER. Self is always present."""
        rows = self._exec(
            "SELECT origin, last_heard_at FROM stx_cursor "
            "WHERE origin <> ? ORDER BY origin",
            (self.origin,),
        ).fetchall()
        return tuple((row[0], row[1]) for row in rows)

    # -- writing ----------------------------------------------------------

    def next_seq(self) -> int:
        row = self._exec(
            "SELECT MAX(seq) FROM stx_oplog WHERE origin = ?", (self.origin,)
        ).fetchone()
        current = 0 if row is None or row[0] is None else int(row[0])
        return current + 1

    def _intent_op(self, intent_id: str):
        row = self._exec(
            "SELECT origin, seq FROM stx_applied_intent WHERE intent_id = ?",
            (intent_id,),
        ).fetchone()
        if row is None:
            return None
        found = self._exec(
            "SELECT origin, seq, table_name, record_key, op, payload, fence, ts "
            "FROM stx_oplog WHERE origin = ? AND seq = ?",
            (row[0], int(row[1])),
        ).fetchone()
        return None if found is None else Op.from_row(found)

    def append(
        self,
        table_name: str,
        record_key: str,
        payload: str = "",
        *,
        op: str = OP_UPSERT,
        intent_id: str = "",
    ) -> Op:
        """Author one op locally. Succeeds while every peer is unreachable.

        With ``intent_id``, the call is idempotent end-to-end: a retry
        after a lost ACK returns the op that ALREADY landed instead of
        appending a second one or reporting a refusal for completed work.
        """
        if intent_id:
            existing = self._intent_op(intent_id)
            if existing is not None:
                return existing
        entry = Op(
            origin=self.origin,
            seq=self.next_seq(),
            table_name=table_name,
            record_key=record_key,
            op=op,
            payload=payload,
            fence=self.fence_for(self.origin),
            ts=utc_now_iso(),
        )
        self.apply(entry)
        if intent_id:
            self._exec(
                "INSERT INTO stx_applied_intent (intent_id, origin, seq, ts) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (intent_id) DO NOTHING",
                (intent_id, entry.origin, entry.seq, entry.ts),
            )
        self.set_cursor(self.origin, entry.seq)
        return entry

    def delete(self, table_name: str, record_key: str, *, intent_id: str = "") -> Op:
        """Delete EXPLICITLY. The only way a deletion enters the system."""
        return self.append(
            table_name, record_key, "", op=OP_DELETE, intent_id=intent_id
        )

    def has_intent(self, intent_id: str) -> bool:
        row = self._exec(
            "SELECT 1 FROM stx_applied_intent WHERE intent_id = ?", (intent_id,)
        ).fetchone()
        return row is not None

    # -- reading the log --------------------------------------------------

    def read_since(self, origin: str, after_seq: int, limit: int = 0) -> tuple:
        sql = _OPLOG_SELECT
        params: tuple = (origin, int(after_seq))
        if limit:
            sql = sql + " LIMIT ?"
            params = params + (int(limit),)
        rows = self._exec(sql, params).fetchall()
        return tuple(Op.from_row(row) for row in rows)

    def origins_in_log(self) -> tuple:
        rows = self._exec(
            "SELECT DISTINCT origin FROM stx_oplog ORDER BY origin", ()
        ).fetchall()
        return tuple(row[0] for row in rows)

    def max_seq(self, origin: str) -> int:
        row = self._exec(
            "SELECT MAX(seq) FROM stx_oplog WHERE origin = ?", (origin,)
        ).fetchone()
        return 0 if row is None or row[0] is None else int(row[0])

    # -- applying ---------------------------------------------------------

    def apply(self, entry: Op) -> None:
        """Durably record and materialise ONE op. Idempotent by construction.

        Applying the same op twice is a no-op: the log insert collides on
        ``(origin, seq)`` and does nothing, and the state upsert is
        guarded by ``stx_record.seq < excluded.seq``, which is false the
        second time round. Nothing here reads a peer, and nothing infers
        anything from a row being absent.
        """
        known = self.fence_for(entry.origin)
        if entry.fence < known:
            raise SupersededFenceError(
                "op {0}#{1} carries fence {2}, superseded by fence {3}".format(
                    entry.origin, entry.seq, entry.fence, known
                )
            )
        if entry.fence > known:
            self.set_fence(entry.origin, entry.fence)

        self._exec(_OPLOG_INSERT, entry.as_row())

        owner = self._exec(
            "SELECT origin FROM stx_record WHERE table_name = ? AND record_key = ?",
            (entry.table_name, entry.record_key),
        ).fetchone()
        if owner is not None and owner[0] != entry.origin:
            raise SingleWriterViolationError(
                "record {0}/{1} is written by {2}; {3} may not write it".format(
                    entry.table_name, entry.record_key, owner[0], entry.origin
                )
            )

        self._exec(
            record_apply_sql(),
            (
                entry.table_name,
                entry.record_key,
                entry.payload,
                1 if entry.is_delete else 0,
                entry.origin,
                entry.seq,
                entry.ts,
            ),
        )
        self._conn.commit()

    # -- reading state ----------------------------------------------------

    def read(self, table_name: str, record_key: str, *, now: float = 0.0) -> Reading:
        """Look up one record and report the uncertainty along with it."""
        moment = now or time.time()
        silences = silences_from(self.heard_pairs(), moment, self.silence_threshold_s)
        row = self._exec(record_select_sql(), (table_name, record_key)).fetchone()
        if row is None:
            return Reading(found=False, watermark=self.watermark(), unheard=silences)
        deleted = bool(row[1])
        return Reading(
            found=not deleted,
            payload="" if deleted else (row[0] or ""),
            owner=row[2],
            watermark=self.watermark(),
            unheard=silences,
        )

    def snapshot(self) -> tuple:
        """Every live record as ``(table, key, payload, origin, seq)``.

        A test-and-report convenience for comparing two HEALED replicas.
        It is deliberately NOT used by replay: comparing stores is the
        mechanism this package exists to avoid.
        """
        rows = self._exec(
            "SELECT table_name, record_key, payload, deleted, origin, seq "
            "FROM stx_record ORDER BY table_name, record_key",
            (),
        ).fetchall()
        return tuple(
            (row[0], row[1], row[2], int(row[3]), row[4], int(row[5])) for row in rows
        )


# EOF
