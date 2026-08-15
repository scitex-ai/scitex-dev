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

from ._errors import OplogGapError, SupersededFenceError
from ._hlc import HLC

__all__ = [
    "FENCE_UNKNOWN",
    "OpEntry",
    "OpKind",
    "assert_contiguous",
    "assert_not_superseded",
]

#: The fence of an origin we have never accepted a fenced op from. Every
#: real fence is >= 1, so an unfenced op can never make a live op look
#: stale, and an origin that has never been fenced is not retroactively
#: judged by a fence it never had.
FENCE_UNKNOWN = 0


def _optional_fence(row: Any) -> int:
    """Read ``fence`` from a row that may predate the column.

    `OpEntry.from_row` is annotated `Mapping[str, Any]`, but the object it
    actually receives from the SQLite dialect is a `sqlite3.Row` — which
    supports `__getitem__` and `keys()` and has NO `.get()`. Reaching for
    the Mapping API the annotation promises raises AttributeError at
    runtime; measured here across 25 tests.

    So this reads through the intersection both types genuinely support,
    and treats a missing column as `FENCE_UNKNOWN` rather than an error:
    oplog tables written before the fence column exist, and refusing to
    read them would turn an additive change into a migration.
    """
    try:
        keys = row.keys()
    except AttributeError:  # a plain Mapping without keys() is still fine
        keys = row
    if "fence" not in keys:
        return FENCE_UNKNOWN
    value = row["fence"]
    return FENCE_UNKNOWN if value is None else int(value)


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
    #: The authority this op was written under — see
    #: :class:`~._errors.SupersededFenceError`. It is a FIELD of the entry
    #: rather than state held beside the log, because an op must carry its
    #: authority to the node that has to judge it. Defaults to
    #: :data:`FENCE_UNKNOWN` so existing unfenced callers keep working;
    #: once an origin issues a real fence, its unfenced ops are stale by
    #: construction, which is the intended behaviour.
    #:
    #: PERSISTED since #539: ``fence`` is one of ``_OPLOG_COLUMNS`` and is
    #: carried by the additive migration in
    #: :meth:`~._peer_state.PeerState._apply_additive_migrations`, so it
    #: survives a round trip on stores that predate the column too.
    fence: int = FENCE_UNKNOWN

    def __post_init__(self) -> None:
        if self.fence < FENCE_UNKNOWN:
            raise ValueError(
                f"OpEntry.fence must be >= {FENCE_UNKNOWN}, got {self.fence!r}. "
                f"{FENCE_UNKNOWN} means 'unfenced'; a negative fence would sort "
                "below it and make an op look older than one written under no "
                "authority at all."
            )
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
            fence=_optional_fence(row),
        )

    def describe(self) -> str:
        """One-line human form for logs and error messages."""
        return f"{self.origin}#{self.seq} {self.op.value} {self.record}"


def assert_not_superseded(
    entries: Sequence[OpEntry], *, fence: int, source: str
) -> None:
    """Verify no entry was authored under a superseded fence.

    A sibling of :func:`assert_contiguous`, and a plain function for the
    same reason: it can be tested on its own, and no code path can apply a
    batch without going through it.

    ``fence`` is the highest fence already accepted from ``source``. An
    entry carrying a LOWER fence was written by an authority that has since
    been superseded — a demoted, partitioned or replaced writer that kept
    running. Such an op is well-formed by every other test in this layer:
    its sequence is contiguous, its clock is honest, its payload is valid.
    Only the fence can reject it.

    :data:`FENCE_UNKNOWN` entries are accepted while ``fence`` is also
    :data:`FENCE_UNKNOWN`, so an origin that has never been fenced is not
    judged by an authority it never had. Once a real fence has been
    accepted from an origin, that origin's unfenced ops ARE stale, and are
    rejected — the transition is the point at which fencing starts to bite.

    Raises :class:`~._errors.SupersededFenceError` naming the offending
    entry, both fences, and the remedy. The class is re-exported from
    ``scitex_dev.store``, so a caller can catch it by name — a fence nobody
    can catch is a crash, not a guard.

    **WIRED INTO REPLAY.** :func:`~._replication.replay` calls this at the
    top of every batch, beside :func:`assert_contiguous` and before anything
    is applied, so a batch carrying a superseded op is rejected WHOLE rather
    than half-written. The persistence it needs — the highest fence accepted
    per origin — is the ``Store.fence`` / ``Store.set_fence`` pair, and
    replay adopts the fence of each entry it accepts, which is what lets a
    LATER batch carrying an older fence be rejected. Without that adoption
    step the check would only ever compare against 0 and could never fire.

    This paragraph previously said the opposite. It read "NOT YET WIRED INTO
    REPLAY ... nothing in the replication path invokes it, so it protects
    nothing" — written when that was true, and left behind when the wiring
    landed. It is recorded rather than quietly deleted because a docstring
    disclaiming a guard that IS running is the more dangerous of the two
    errors: a reader who trusts it concludes the fence is inert and looks
    elsewhere for the cause of a rejected batch.
    """
    if not entries:
        return

    for entry in entries:
        if entry.fence >= fence:
            continue
        authored = (
            "no fence at all" if entry.fence == FENCE_UNKNOWN
            else f"fence {entry.fence}"
        )
        raise SupersededFenceError(
            f"{source}: {entry.describe()} was authored under {authored}, but "
            f"fence {fence} has already been accepted from this origin. The "
            "writer that produced this op is no longer the authority for it — "
            "it was most likely demoted, partitioned away, or replaced, and "
            "kept running.\n"
            "This op is valid by every other check: its sequence is "
            "contiguous, its clock is honest, its payload parses. Field-level "
            "merge would resolve it on RECENCY and let it win, because merge "
            "has no opinion on who was ENTITLED to write.\n"
            f"Remedy: stop the writer still emitting fence {entry.fence} for "
            f"{source}. If fence {fence} is itself wrong, correct it at the "
            "source and re-issue — never by accepting this op."
        )


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
