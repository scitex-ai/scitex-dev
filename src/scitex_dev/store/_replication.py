#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Directed replay — the only sanctioned way two stores reconcile.

The rule, and the incident behind it
------------------------------------
**No code may delete a row because it is absent from another store.**
That is scitex-cards' ruling (ADR-0016), written after three board wipes on
2026-07-19/21, one of which replaced 2,159 live rows with a 5-row temporary
document. The mechanism, in their words: *"reconciling two stores treated
as PEERS, where absence in one is interpreted as deletion in the other."*

Set-difference reconciliation cannot express that rule, because absence is
its only input. Given "row here, not there" it must choose a meaning, and
whichever it chooses is wrong half the time — silently.

Directed replay never asks what the other side HAS. It asks what the other
side DID, in order, and applies it. Absence from a log is not evidence of
anything, so the destructive inference is not merely discouraged: it is
unavailable. There is no code path in this module that removes a row, and
none can be added without also adding a delete verb to the store, which
does not have one.

The assertion that makes it true
--------------------------------
Replay is only safe if the log is provably complete up to where it stops.
:func:`replay` therefore refuses any batch whose first sequence is not
exactly ``cursor + 1``, and any batch with an internal hole. A gap means
ops were never seen; applying what came after would put a later state on
top of an unseen earlier one and leave two replicas silently different.

If that assertion fires, the fix is to re-request from ``cursor + 1``. It
is never to widen the assertion — a check that cannot fail is the same as
no check, except that everyone believes it is working.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from ._merge import MergeConflict
from ._oplog import OpEntry, assert_contiguous, assert_not_superseded
from ._store import Store

__all__ = ["ReplayResult", "pull", "replay", "sync"]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """What a replay did — a fixed shape, every signal its own field.

    ``applied`` and ``conflicts`` are separate because a conflict is not a
    failure: the op still applied, a merge rule reported that it could not
    reconcile two values, and the caller may want to look. Folding them
    into one count would make "12 applied" ambiguous.
    """

    source: str
    applied: int
    cursor_before: int
    cursor_after: int
    conflicts: tuple[MergeConflict, ...] = field(default=())

    @property
    def advanced(self) -> bool:
        """Whether the cursor moved."""
        return self.cursor_after > self.cursor_before

    def describe(self) -> str:
        """One line for logs and card notes."""
        return (
            f"replay {self.source}: {self.applied} op(s), cursor "
            f"{self.cursor_before} -> {self.cursor_after}"
            + (f", {len(self.conflicts)} conflict(s)" if self.conflicts else "")
        )


def replay(store: Store, source: str, entries: Sequence[OpEntry]) -> ReplayResult:
    """Apply ``entries`` from ``source`` to ``store``, in order.

    Verifies contiguity against the store's cursor BEFORE applying
    anything, so a bad batch is rejected whole rather than half-applied.

    ATOMIC PER BATCH. The whole replay runs inside one
    :meth:`~._store.Store.batch` transaction: it either applies completely
    and advances the cursor, or applies nothing and leaves the cursor where
    it was. This REPLACED per-entry commits, and the change is deliberate on
    two counts.

    Correctness: a crash mid-batch used to leave a partially-applied batch
    behind a cursor describing it. That was consistent, but it made "what is
    applied" a function of when the process died. Now it is a function of
    what succeeded. The next pull re-requests from the unchanged cursor and
    re-applies the whole batch, which is safe because an op folds to the same
    state however many times it is applied.

    Cost: the old shape paid one commit per statement, three per op.
    Measured at both scales, since they could have differed in sign —
    8.99 -> 1.04 ms/op over sixty five-op replays, and 18.59 -> 2.06 ms/op
    adopting the real 3,712-card board. Small batches are the common case
    here, so the first number is the one that matters for catch-up.

    Raises :class:`~._errors.OplogGapError` if the batch does not start at
    ``cursor + 1``, has an internal hole, or mixes origins.
    """
    cursor_before = store.cursor(source)
    ordered = list(entries)
    assert_contiguous(ordered, cursor=cursor_before, source=source)
    # Contiguity proves nothing was MISSED. The fence proves the writer was
    # still ENTITLED — a demoted or partitioned peer that keeps running emits
    # ops that pass every other check here. Both run BEFORE anything is
    # applied, so a bad batch is rejected whole rather than half-applied.
    assert_not_superseded(ordered, fence=store.fence(source), source=source)

    conflicts: list[MergeConflict] = []
    applied = 0
    cursor = cursor_before
    with store.batch():
        for entry in ordered:
            result = store.apply_remote(entry)
            conflicts.extend(result.conflicts)
            cursor = entry.seq
            store.set_cursor(source, cursor)
            # Adopt the authority we just accepted under, so a LATER batch
            # carrying an older fence is rejected. Without this the check
            # above only ever compares against 0 and can never fire.
            if entry.fence > store.fence(source):
                store.set_fence(source, entry.fence)
            applied += 1

    return ReplayResult(
        source=source,
        applied=applied,
        cursor_before=cursor_before,
        cursor_after=cursor,
        conflicts=tuple(conflicts),
    )


def pull(local: Store, remote: Store, source: str, *, batch: int = 1000) -> ReplayResult:
    """Fetch one batch of ``source``'s ops from ``remote`` and replay them.

    ``source`` is usually ``remote.node``, but not always: a store relays
    ops it replayed from a third node, and those keep their ORIGINAL
    origin. Sequence numbers belong to whoever minted them, so relaying
    never renumbers.
    """
    cursor = local.cursor(source)
    entries = remote.changes_since(source, cursor, limit=batch)
    return replay(local, source, entries)


def sync(local: Store, remote: Store, *, batch: int = 1000) -> list[ReplayResult]:
    """Replay every origin ``remote`` knows about into ``local``.

    One direction only. Call it twice with the arguments swapped for a
    two-way sync — deliberately, so each direction's result is inspected
    separately rather than merged into one number that hides a failure.

    Origins are replayed in a stable order, and ``local``'s own ops are
    skipped: a node does not replay its own writes back into itself.
    """
    results: list[ReplayResult] = []
    for source in sorted(remote.origins()):
        if source == local.node:
            continue
        results.append(pull(local, remote, source, batch=batch))
    return results


def outstanding(local: Store, remote: Store) -> dict[str, int]:
    """How many ops per origin ``local`` has not yet applied from ``remote``.

    A pure question — it applies nothing. Useful as a monitoring signal:
    an origin whose backlog grows without bound means replay is failing or
    nobody is calling it, and both look identical from the outside.
    """
    behind: dict[str, int] = {}
    for source, highest in remote.origins().items():
        if source == local.node:
            continue
        gap = highest - local.cursor(source)
        if gap > 0:
            behind[source] = gap
    return behind


def replay_all(store: Store, batches: Iterable[tuple[str, Sequence[OpEntry]]]) -> list[ReplayResult]:
    """Replay several ``(source, entries)`` batches, one source at a time.

    Sequence numbers are per-origin, so batches are never interleaved: each
    source is applied whole, in its own order, against its own cursor.
    """
    return [replay(store, source, entries) for source, entries in batches]

# EOF
