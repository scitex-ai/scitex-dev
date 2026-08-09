#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The operation log — an ordered, gapless, append-only record of intent.

Why a log at all
----------------
Because the alternative is comparing states, and comparing states cannot
tell "this row was never sent to me" apart from "this row was removed".
Both look like *absence*. **Three board wipes on 2026-07-19/21** resolved
that ambiguity the destructive way; one replaced **2,159 live rows** with
a 5-row temporary document. (ADR-0016, dated 2026-07-30, is the analysis
— not the event.) Its ruling names the mechanism: *"reconciling two
stores treated as PEERS, where absence in one is interpreted as deletion
in the other"*, and the invariant that follows: *"No code may delete a row
because it is absent from another store."*

A log removes the ambiguity at the source: it never says what *is*, only
what *happened*. Absence from a log is not evidence of anything, so no
amount of misreading it can produce a deletion.

The gapless invariant
---------------------
``seq`` is per-ORIGIN — the node that accepted the write — starting at 1
and increasing by exactly one. It is the primary key together with
``origin``, so the database itself refuses a duplicate.

Origin, not owner. Sequence numbers must come from whoever *accepted* the
write, because that is the only party in a position to number them
consecutively. Keying them by a record's logical owner would break the
moment ownership is reassigned by somebody else — which is the normal
case in the fleet's first consumer, where the operator resolves a card
from a different host than its assignee.

That contiguity is what lets a consumer *prove* it has seen everything up
to its cursor — see :func:`~._replication.replay` and its
``first_seq == cursor + 1`` assertion. Without gaplessness the assertion
would be unenforceable and directed replay would be no safer than the
set-difference it replaces.

Ops are intents, not states
---------------------------
``UPSERT`` carries only the fields that changed, not the whole row. Two
writers touching different fields of one record therefore do not clobber
each other, and a replayed op applies the same way whether the target has
seen one prior op or a hundred.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from ._errors import OplogGapError
from ._hlc import HLC

__all__ = ["OpEntry", "OpKind", "assert_contiguous"]


class OpKind(str, Enum):
    """What an op does. There is deliberately no ``DELETE``."""

    #: Set one or more fields. Payload is ``{field: value}``.
    UPSERT = "upsert"
    #: Set the hide flag. Payload is ``{}``.
    HIDE = "hide"
    #: Clear the hide flag. Payload is ``{}``.
    UNHIDE = "unhide"
    #: Transfer single-writer ownership. Payload is ``{"to": <writer>}``.
    #: Only the current owner may append one.
    HANDOVER = "handover"


@dataclass(frozen=True, slots=True)
class OpEntry:
    """One entry in the log.

    ``origin`` is the node that ACCEPTED the write and owns the sequence
    numbering. ``actor`` is who performed it — an agent id, the operator —
    and is domain information: it never affects replay order.
    """

    origin: str
    seq: int
    record: str
    op: OpKind
    payload: Mapping[str, Any]
    hlc: HLC
    actor: str = ""

    def __post_init__(self) -> None:
        if self.seq < 1:
            raise ValueError(
                f"OpEntry.seq must start at 1, got {self.seq!r}. Sequence 0 is "
                "reserved for 'nothing applied yet' in the replay cursor; "
                "allowing an op at 0 would make an empty cursor "
                "indistinguishable from one entry already applied."
            )
        if not self.origin:
            raise ValueError(
                "OpEntry.origin must name the node that accepted the write. "
                "Sequence numbers are per-origin; an unnamed origin makes the "
                "replay cursor meaningless."
            )
        if not self.record:
            raise ValueError("OpEntry.record must name the record key.")
        if self.op is OpKind.HANDOVER and not self.payload.get("to"):
            raise ValueError(
                "A HANDOVER op must carry payload {'to': <new owner>} — "
                "ownership cannot be transferred to nobody."
            )

    # -- serialisation ----------------------------------------------------
    def payload_json(self) -> str:
        """The payload as stored. Sorted keys keep it diffable."""
        return json.dumps(self.payload, sort_keys=True, default=str)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "OpEntry":
        """Rebuild from a database row of the oplog table."""
        return cls(
            origin=row["origin"],
            seq=int(row["seq"]),
            record=row["record"],
            op=OpKind(row["op"]),
            payload=json.loads(row["payload"]),
            hlc=HLC.decode(row["hlc"]),
            actor=row["actor"] or "",
        )

    def describe(self) -> str:
        """One-line human form for logs and error messages."""
        return f"{self.origin}#{self.seq} {self.op.value} {self.record}"


def assert_contiguous(entries: Sequence[OpEntry], *, cursor: int, source: str) -> None:
    """Verify a replay batch continues exactly at ``cursor + 1``.

    **This is the load-bearing check of the whole replication layer.** It
    is a plain function so it can be tested on its own and so no code path
    can apply a batch without going through it.

    Raises :class:`~._errors.OplogGapError` when the batch does not start
    at ``cursor + 1``, when it is not strictly increasing by one, or when
    any entry comes from a different writer than ``source``.
    """
    if not entries:
        return

    expected = cursor + 1
    first = entries[0]
    if first.seq != expected:
        if first.seq > expected:
            detail = (
                f"missing {first.seq - expected} op(s) — sequences "
                f"{expected}..{first.seq - 1} were never received"
            )
            remedy = (
                f"Re-request the batch starting at seq {expected}. Do NOT "
                "widen or remove this assertion: applying a later state on "
                "top of an unseen earlier one is exactly how divergence "
                "becomes silent."
            )
        else:
            detail = (
                f"batch replays already-applied op(s) — cursor is at "
                f"{cursor} but the batch starts at {first.seq}"
            )
            remedy = (
                f"Request from seq {expected} instead. Re-applying old ops "
                "would move field timestamps backwards."
            )
        raise OplogGapError(
            f"Oplog gap replaying source {source!r}: {detail}. {remedy}"
        )

    previous = first
    for entry in entries[1:]:
        if entry.seq != previous.seq + 1:
            raise OplogGapError(
                f"Oplog gap replaying source {source!r}: op "
                f"{previous.describe()} is followed by {entry.describe()}, "
                f"skipping seq {previous.seq + 1}. The log a peer serves must "
                "be contiguous; a hole means its own store lost entries. "
                "Re-request the batch, and check that peer's oplog table for "
                "missing sequence numbers."
            )
        previous = entry

    wrong_source = sorted({e.origin for e in entries if e.origin != source})
    if wrong_source:
        raise OplogGapError(
            f"Replay batch for source {source!r} contains ops from origin(s) "
            f"{wrong_source}. Sequence numbers are per-origin, so mixing "
            "origins into one batch makes the cursor meaningless. Replay one "
            "origin at a time."
        )

# EOF
