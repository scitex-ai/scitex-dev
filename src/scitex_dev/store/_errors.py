#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Error hierarchy for :mod:`scitex_dev.store`.

Every error here carries an ACTIONABLE hint — the constitution's
"an error that only states what broke is half-written" rule. Each one
names the offending field / writer / sequence number and the next step.

Nothing in this module is a warning. A store primitive that degrades
silently is worse than one that refuses: the caller keeps writing and
only discovers the damage when rows are already gone.
"""

from __future__ import annotations

__all__ = [
    "AdoptionRefusedError",
    "ClockDriftError",
    "DialectUnavailableError",
    "FieldPolicyError",
    "OplogGapError",
    "RecordNotFoundError",
    "RevisionMismatchError",
    "SchemaError",
    "StoreError",
    "StoreTargetError",
    "SupersededFenceError",
    "WriterConflictError",
]


class StoreError(Exception):
    """Base class for every :mod:`scitex_dev.store` failure."""


class SchemaError(StoreError):
    """A schema could not be constructed as declared."""


class FieldPolicyError(SchemaError):
    """A field's policy is missing or malformed.

    Raised at SCHEMA CONSTRUCTION time, never at write time. There is no
    default policy to fall back on — see :class:`~._policy.FieldPolicy`.
    """


class StoreTargetError(StoreError):
    """A store target is unusable — bad locator, unknown backend."""


class AdoptionRefusedError(StoreError):
    """Bringing an existing dataset under the primitive would merge two of them.

    Adoption mints a GENESIS log: one op per pre-existing record, describing
    a history the primitive did not witness. Installing that log into a store
    that already holds rows does not replace them and cannot fail loudly —
    the ops are well-formed, so field-level merge folds two unrelated
    datasets together on recency and reports success.

    The distinction the store cannot make for itself is WHY those rows are
    there. A store seeded by replay from a peer already holds the data and
    must not adopt; a genuinely fresh store must. Both look identical from
    inside, so the caller is asked rather than guessed at.
    """


class DialectUnavailableError(StoreError):
    """A backend was requested whose driver is not installed.

    Deliberately NOT a fallback to SQLite. Silently answering a Postgres
    request with a local SQLite file would hand the caller a store that
    looks healthy and shares nothing.
    """


class RecordNotFoundError(StoreError):
    """A write named an expected revision for a record that does not exist.

    Distinct from :class:`RevisionMismatchError` on purpose: "never existed"
    and "moved on since you read it" call for different responses, and
    collapsing them into one error makes the caller guess.
    """


class RevisionMismatchError(StoreError):
    """An optimistic-lock write lost the race.

    The store writes with ``WHERE <key> = ? AND _revision = ?`` and requires
    the affected-row count to be exactly 1. A plain row-level UPDATE without
    this check still loses updates when two writers touch the same field —
    which is why the lock is required rather than offered.

    The caller's move is to re-read, re-apply its intent to the new value,
    and retry. It is NOT to retry with the same revision, and it is not to
    switch to an unlocked write.
    """


class ClockDriftError(StoreError):
    """A remote HLC timestamp is implausibly far ahead of this host.

    Accepting it would drag the local clock forward permanently, so every
    subsequent honest local write would lose last-writer-wins forever.
    Failing here bounds the damage to one rejected batch.
    """


class WriterConflictError(StoreError):
    """A writer tried to append an op for a record it does not own.

    Raised only by stores running under
    :attr:`~._policy.WriterPolicy.SINGLE_WRITER`. Ownership then moves
    solely through an explicit hand-over op appended BY THE CURRENT OWNER.

    Multi-writer stores never raise this: for them ownership is an
    ordinary domain field, not the replication key. See
    :class:`~._policy.WriterPolicy` for why both modes exist.
    """


class OplogGapError(StoreError):
    """A replay batch does not continue exactly where the cursor stopped.

    THIS IS THE LOAD-BEARING ASSERTION of the replication layer.

    The incident it exists for: **three board wipes on 2026-07-19/21**,
    one of which replaced **2,159 live rows** with a 5-row temporary
    document. (2026-07-30 is the date of ADR-0016, which analysed them —
    not the date of the event. Searching the log for 07-30 finds the
    postmortem and misses the incident.) scitex-cards' ruling states the
    mechanism exactly: *"reconciling two stores treated as PEERS, where
    absence in one is interpreted as deletion in the other."*

    Directed replay cannot make that inference at all — a log says only
    what happened, never what exists, so absence from it is not evidence
    of anything. But that guarantee holds only if the log is provably
    contiguous. A gap means some ops were never seen, and continuing past
    it would apply a later state on top of an unseen earlier one.

    Recovery is to re-request the batch starting at ``cursor + 1``, not
    to lower the assertion.
    """


class SupersededFenceError(StoreError):
    """An op was authored under a fence lower than one already accepted.

    A FENCE is a monotone integer an origin writes under. It answers a
    question neither the cursor nor the HLC can: **was this writer still
    entitled to write?**

    Contiguity proves nothing was MISSED. Ordering proves what came FIRST.
    Neither notices a writer that was demoted, partitioned away, or
    replaced, kept running, and is still emitting well-formed ops with
    correct sequence numbers and honest clocks. Those ops are valid by
    every other test in this layer, and applying them silently resurrects
    state from a node that is no longer authoritative.

    Under Decision 9 (multi-writer) this hazard is if anything sharper
    than it was under the rejected single-writer model. Field-level merge
    resolves WHO WROTE LAST; it has no opinion on WHO WAS ALLOWED TO. A
    demoted writer's field simply wins on recency.

    The fence therefore lives in the log as a COLUMN of each op, not as a
    value held beside it: an op must carry the authority it was written
    under, or that authority does not survive replication to the node
    that has to judge it.

    Recovery is to stop the superseded writer, not to lower the fence. If
    the fence itself is wrong, correct it at the source and re-issue —
    never by accepting an op that failed this check.
    """

# EOF
