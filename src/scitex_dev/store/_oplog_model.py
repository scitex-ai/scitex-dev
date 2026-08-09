#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The oplog record, and the narrow set of failures replay is allowed to have.

Reconciliation in this package is DIRECTED REPLAY of an ordered log --
never a comparison of two stores. That distinction is not stylistic. A
comparison reads ABSENCE as evidence, and on 2026-07-30 that reading
destroyed 2,159 rows in this house: a record missing on one side was
taken for a deletion on the other, and the "sync" faithfully propagated
a deletion nobody had ever performed. Replay is structurally incapable
of that mistake because absence is never an input to any decision it
makes -- it carries one monotone integer per origin and asks a single
question, "what came after N?".

Single-writer-per-record makes ``(origin, seq)`` the causal order
outright, so there are no conflicts to detect, no Lamport or vector
clocks to keep, and no tombstones to garbage-collect. What CAN still go
wrong is small and enumerable, and every member of that set RAISES:

* :class:`OplogGapError` -- the log is not contiguous from the cursor.
  A gap that merely warned would replicate as "caught up", which is the
  silent-loss path that sank the automatic-merge designs.
* :class:`SupersededFenceError` -- an op authored under a fence that has
  since been superseded. Without the fence a demoted writer's ops
  replicate as legitimate, so the fence is a COLUMN of the oplog
  (:data:`OPLOG_COLUMNS`), not a value held beside it.
* :class:`SingleWriterViolationError` -- two origins wrote one record.
  The model says this cannot happen; if it does, the model is wrong and
  saying so is worth more than silently picking a winner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .._core.errors import ErrorCode, ScitexError

__all__ = [
    "FENCE_UNKNOWN",
    "OPLOG_COLUMNS",
    "OP_DELETE",
    "OP_KINDS",
    "OP_UPSERT",
    "Op",
    "OplogGapError",
    "SingleWriterViolationError",
    "StoreReplayError",
    "SupersededFenceError",
    "UnknownOpKindError",
    "utc_now_iso",
]

#: A record is written (created or overwritten) by its owning origin.
OP_UPSERT = "upsert"

#: A record is deleted BY ITS OWNER, EXPLICITLY. This is the only way a
#: deletion ever enters the system. Nothing infers a deletion from a row
#: being missing somewhere -- that inference is the 2026-07-30 defect.
OP_DELETE = "delete"

OP_KINDS = frozenset({OP_UPSERT, OP_DELETE})

#: Column order of the append-only oplog table. ``fence`` sits HERE, in the
#: row, so that an op carries the authority it was written under wherever it
#: travels. A fence kept beside the log instead of in it cannot survive
#: replication, and a superseded writer's ops then arrive indistinguishable
#: from a current writer's.
OPLOG_COLUMNS = (
    "origin",
    "seq",
    "table_name",
    "record_key",
    "op",
    "payload",
    "fence",
    "ts",
)

#: The fence of an origin we have never accepted an op from. Every real
#: fence is >= 1, so an unknown origin can never make a live op look stale.
FENCE_UNKNOWN = 0


class StoreReplayError(ScitexError):
    """Base for every replay refusal. Always raised, never logged-and-skipped."""

    default_code = ErrorCode.CONFLICT
    default_remediation = ""

    def __init__(self, message: str, *, code=None, remediation=None) -> None:
        super().__init__(
            message,
            code=code or self.default_code,
            remediation=remediation or self.default_remediation or None,
        )


class OplogGapError(StoreReplayError):
    """The batch does not start at ``cursor + 1``, so the log lost an op.

    This is THE safety property of the replay layer. Downgrading it to a
    warning, or skipping ahead to the first available seq, turns a hole in
    the log into a replica that reports itself CAUGHT UP while permanently
    missing writes -- loss that no later pass can even detect.
    """

    default_remediation = (
        "Do NOT advance the cursor past a gap. Recover the missing ops from "
        "the origin's log (it is append-only, so they either exist or the "
        "origin lost them), then replay again from the same cursor."
    )


class SupersededFenceError(StoreReplayError):
    """The op was authored under a fence lower than one already accepted."""

    default_remediation = (
        "Discard the demoted writer's log: only ops at or above the origin's "
        "current fence may be replayed. If the fence is wrong, correct it at "
        "the origin -- never lower it on the replica to admit the op."
    )


class UnknownOpKindError(StoreReplayError):
    """The op kind is not in :data:`OP_KINDS` -- refuse rather than guess."""

    default_code = ErrorCode.VALIDATION
    default_remediation = "Use one of: {0}.".format(", ".join(sorted(OP_KINDS)))


class SingleWriterViolationError(StoreReplayError):
    """Two origins claim the same record; the causal order is not defined."""

    default_remediation = (
        "Exactly one host may write a given record -- that is what makes "
        "(origin, seq) a causal order. Re-partition record ownership so the "
        "two writers no longer overlap."
    )


def utc_now_iso() -> str:
    """Timezone-aware UTC stamp. Ordering is by ``seq``; this is for humans."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Op:
    """One append-only entry: what changed, who says so, and under what fence.

    ``seq`` is a per-origin monotone integer starting at 1. Because exactly
    one host may write a given record, ``(origin, seq)`` IS the causal
    order -- there is nothing further to reconcile and nothing to compare.
    """

    origin: str
    seq: int
    table_name: str
    record_key: str
    op: str
    payload: str
    fence: int
    ts: str = ""

    def __post_init__(self) -> None:
        if self.op not in OP_KINDS:
            raise UnknownOpKindError(
                "unknown op kind {0!r}; expected one of {1}".format(
                    self.op, sorted(OP_KINDS)
                )
            )
        if self.seq < 1:
            raise ValueError("seq must be >= 1, got {0!r}".format(self.seq))

    @property
    def is_delete(self) -> bool:
        return self.op == OP_DELETE

    def as_row(self) -> tuple:
        """Values in :data:`OPLOG_COLUMNS` order, for a positional INSERT."""
        return (
            self.origin,
            self.seq,
            self.table_name,
            self.record_key,
            self.op,
            self.payload,
            self.fence,
            self.ts,
        )

    @classmethod
    def from_row(cls, row) -> "Op":
        """Rebuild from a row selected in :data:`OPLOG_COLUMNS` order."""
        return cls(
            origin=row[0],
            seq=int(row[1]),
            table_name=row[2],
            record_key=row[3],
            op=row[4],
            payload=row[5] or "",
            fence=int(row[6]),
            ts=row[7] or "",
        )

    def to_dict(self) -> dict:
        return {
            "origin": self.origin,
            "seq": self.seq,
            "table": self.table_name,
            "record_key": self.record_key,
            "op": self.op,
            "payload": self.payload,
            "fence": self.fence,
            "ts": self.ts,
        }


# EOF
