#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Directed replay: the ONLY way state moves between replicas here.

The whole algorithm is: *ask one host for the ops that follow the integer
I already have, verify they follow it, apply them, advance the integer.*
There is no snapshot, no diff, no set subtraction, no "present here but
missing there". This module never reads the target's records at all --
its only input from the target is one monotone integer per origin.

That is a deliberate structural property, not an implementation detail.
The rejected alternative -- compare two stores and sync the difference --
is what destroyed 2,159 rows in this house on 2026-07-30: absence in one
store was read as a deletion in the other and dutifully applied. Replay
is cheaper than the comparison it replaces AND cannot express that bug,
because absence is never an input to any decision it makes.

:func:`replay` refuses rather than degrades. In particular the check

    first_seq == cursor + 1

is the core safety property of this layer. A gap in the log means ops
were lost; without this assertion the replica would consume whatever
happened to be available, advance its cursor past the hole, and report
itself CAUGHT UP while permanently missing writes. It raises
:class:`~._oplog_model.OplogGapError`. It does not warn, and it does not
skip.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._oplog_model import OplogGapError

__all__ = ["ReplayOutcome", "heal", "replay", "replay_all"]

#: Ops fetched per round trip. Bounded so a long-partitioned peer streams
#: instead of materialising its whole log in memory; contiguity is checked
#: per batch AND across batch boundaries, so batching never widens the hole
#: the assertion is there to catch.
DEFAULT_BATCH_SIZE = 500

#: Refuse to loop forever if a source keeps returning ops that never
#: advance the cursor. That would mean the source violates its own
#: ordering contract, which is a bug to surface, not to spin on.
MAX_BATCHES = 100_000


@dataclass(frozen=True)
class ReplayOutcome:
    """What one directed replay actually did. Never merely "ok"."""

    origin: str
    cursor_before: int
    cursor_after: int
    applied: int = 0
    batches: int = 0
    exhausted: bool = True

    @property
    def caught_up(self) -> bool:
        """True only if the source ran OUT of ops, not if we gave up early."""
        return self.exhausted

    @property
    def moved(self) -> bool:
        return self.cursor_after > self.cursor_before

    def to_dict(self) -> dict:
        return {
            "origin": self.origin,
            "cursor_before": self.cursor_before,
            "cursor_after": self.cursor_after,
            "applied": self.applied,
            "batches": self.batches,
            "moved": self.moved,
            "caught_up": self.caught_up,
        }


def _assert_contiguous(ops, cursor: int, origin: str) -> None:
    """The batch must continue the log EXACTLY, with no hole anywhere.

    Two separate ways a hole can appear, both fatal: the batch may not
    start where the cursor left off, or it may skip a seq internally.
    """
    expected = cursor + 1
    first = ops[0].seq

    # Property 1 -- THE core safety property. The batch must CONTINUE the
    # cursor. Without this, a replica consumes whatever the source happens
    # to still hold, advances its cursor past the hole, and reports itself
    # caught up while permanently missing writes.
    if first != expected:
        raise OplogGapError(
            "gap in {0}'s oplog: cursor at {1} expects seq {2}, "
            "next available op is seq {3} -- {4} op(s) lost".format(
                origin, cursor, expected, first, first - expected
            )
        )

    # Property 2 -- no hole INSIDE the batch. Checked relative to the
    # batch's own first seq so that it stays INDEPENDENT of property 1:
    # each covers a hole the other cannot see, and neither stands in for
    # the other if it is ever weakened.
    for offset, entry in enumerate(ops):
        wanted = first + offset
        if entry.seq != wanted:
            raise OplogGapError(
                "gap inside {0}'s batch: expected seq {1}, got seq {2}".format(
                    origin, wanted, entry.seq
                )
            )


def replay(source, target, origin: str, *, batch_size: int = DEFAULT_BATCH_SIZE):
    """Replay ``origin``'s ops from ``source`` into ``target`` until caught up.

    Returns a :class:`ReplayOutcome`. Raises
    :class:`~._oplog_model.OplogGapError` on a hole in the log and
    :class:`~._oplog_model.SupersededFenceError` on an op authored under a
    fence that has since been superseded. Applying is idempotent, so a
    call interrupted part-way is resumed -- not repaired -- by calling it
    again.
    """
    cursor_before = target.cursor_for(origin)
    cursor = cursor_before
    applied = 0
    batches = 0
    exhausted = False

    while batches < MAX_BATCHES:
        ops = source.read_since(origin, cursor, batch_size)
        if not ops:
            exhausted = True
            break
        _assert_contiguous(ops, cursor, origin)
        for entry in ops:
            target.apply(entry)
        cursor = ops[-1].seq
        target.set_cursor(origin, cursor)
        applied += len(ops)
        batches += 1

    target.touch(source.origin)
    return ReplayOutcome(
        origin=origin,
        cursor_before=cursor_before,
        cursor_after=cursor,
        applied=applied,
        batches=batches,
        exhausted=exhausted,
    )


def replay_all(source, target, *, batch_size: int = DEFAULT_BATCH_SIZE) -> tuple:
    """Replay every origin ``source`` holds a log for, in a stable order."""
    return tuple(
        replay(source, target, origin, batch_size=batch_size)
        for origin in source.origins_in_log()
    )


def heal(left, right, *, batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """Replay BOTH directions after a partition. Order is irrelevant.

    Each side authored only the records it owns, so neither direction can
    overwrite the other's work and no ordering between the two passes can
    change the result.
    """
    return {
        "{0}->{1}".format(left.origin, right.origin): replay_all(
            left, right, batch_size=batch_size
        ),
        "{0}->{1}".format(right.origin, left.origin): replay_all(
            right, left, batch_size=batch_size
        ),
    }


# EOF
