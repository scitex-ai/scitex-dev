#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adoption — bringing a database that already exists under the primitive.

Every guarantee in this package is a property of the OPLOG. A store with no
log has no history to replay, so :func:`~._replication.sync` has nothing to
send and the contiguity assertion has nothing to assert. That is not a
degraded mode: it is the set-difference world the primitive was written to
replace, and a store can sit in it while looking entirely healthy.

Existing data therefore cannot simply be pointed at the primitive. It has
to be given a history — one op per pre-existing record, describing a past
the primitive did not witness. That is what a GENESIS log is.

Why genesis is built once and SHARED, not minted per host
---------------------------------------------------------
The obvious approach is: each host adopts its own copy. It is also a silent
lost-update generator, and the fleet is currently standing in exactly the
position that triggers it — three hosts holding byte-identical copies of one
board.

Suppose host A and host B each adopt the same 3,708 records. A's log is
``origin=A, seq 1..3708``; B's is ``origin=B, seq 1..3708``. Both are
well-formed. Now A makes a real edit, then syncs from B. B's genesis ops are
unknown to A, contiguous, and stamped whenever B ran adoption — which may be
AFTER A's edit. Last-writer-wins compares stamps, not provenance, so B's
*snapshot of the old value* overwrites A's *newer real edit*. Nothing raises.
The op was valid; the merge did its job; the edit is gone.

So genesis is built ONCE, under a shared origin that names the adoption
rather than any host, and the identical log is installed everywhere. Two
hosts holding the same genesis are byte-identical over that range, so replay
between them is a no-op for it and only real post-adoption ops flow. The
hazard is not mitigated, it is absent — there is no second genesis to
conflict with.

This mirrors the fleet's SIF decision (build centrally, distribute the
artefact) for the same reason: an artefact built once and copied cannot
disagree with itself, and one built N times will.

Determinism is what makes that true
-----------------------------------
:func:`build_genesis` takes an explicit ``at_us`` and derives every stamp
from it, sorts records by key, and never reads the wall clock. Two runs over
the same input produce byte-identical logs. If it sampled ``time.time()``
the "shared" genesis would differ per host and the hazard above would come
straight back, disguised as a distribution problem.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from ._errors import AdoptionRefusedError, StoreError
from ._guards import record_key
from ._hlc import HLC
from ._oplog import FENCE_UNKNOWN, OpEntry, OpKind
from ._policy import Schema
from ._replication import ReplayResult, replay
from ._store import Store

__all__ = [
    "GENESIS_ACTOR",
    "build_genesis",
    "genesis_origin",
    "install_genesis",
    "verify_adoption",
]

#: The actor recorded on every genesis op. A fixed, greppable value: these
#: ops describe records the primitive never saw written, and attributing
#: them to whichever agent happened to run the migration would put a false
#: author on 3,708 rows of history.
GENESIS_ACTOR = "adopt:genesis"


def genesis_origin(dataset: str, stamp: str) -> str:
    """The shared origin label a genesis log is minted under.

    Deliberately NOT a hostname. The origin is the replication coordinate,
    and naming a host here would make the log that host's — every other host
    would then be replaying a peer's history rather than installing the same
    artefact, which is the failure this module exists to avoid.

    ``stamp`` distinguishes re-adoptions of the same dataset (a second
    migration after a schema change), so the two never share a sequence
    space.
    """
    if not dataset or not stamp:
        raise StoreError(
            "genesis_origin needs both a dataset name and a stamp — the "
            "origin must be unique per adoption, or a later re-adoption "
            "reuses sequence numbers the first one already spent."
        )
    return f"genesis:{dataset}@{stamp}"


def build_genesis(
    schema: Schema,
    records: Iterable[Mapping[str, Any]],
    *,
    origin: str,
    at_us: int,
    actor: str = GENESIS_ACTOR,
    fence: int = FENCE_UNKNOWN,
) -> list[OpEntry]:
    """Mint a portable genesis log for ``records``. Pure and deterministic.

    Touches no database and no clock. The result is an ordered, gapless,
    origin-consistent batch that :func:`install_genesis` (or plain
    :func:`~._replication.replay`) can apply to any number of stores.

    ``at_us`` is the wall component every stamp is derived from, in
    microseconds. Pass the time the SOURCE data was snapshotted, not "now" —
    genesis describes history, and stamping it later than real subsequent
    edits would make the snapshot win last-writer-wins against them.
    """
    if at_us <= 0:
        raise StoreError(
            f"build_genesis needs a positive at_us, got {at_us!r}. It is the "
            "wall component of every genesis stamp; zero would place the "
            "whole dataset at the epoch, behind any real write, and make the "
            "ordering meaningless."
        )
    if not origin:
        raise StoreError(
            "build_genesis needs an origin — use genesis_origin() so the "
            "label names the adoption rather than a host."
        )

    keyed: dict[str, Mapping[str, Any]] = {}
    for record in records:
        unknown = sorted(name for name in record if name not in schema.fields)
        if unknown:
            raise StoreError(
                f"Cannot adopt a record carrying field(s) {unknown} that "
                f"schema {schema.name!r} does not declare. Known fields: "
                f"{sorted(schema.fields)}. Every adopted column needs a "
                "FieldPolicy, because a column with no merge rule cannot be "
                "reconciled and would be dropped on the first sync."
            )
        key = record_key(schema, record)
        if key in keyed:
            raise StoreError(
                f"Cannot adopt: two source records share the identity key "
                f"{key!r}. Genesis mints one op per record, so a duplicate "
                "key would silently collapse two rows into one. De-duplicate "
                "at the source, where it is visible which row to keep."
            )
        keyed[key] = dict(record)

    return [
        OpEntry(
            origin=origin,
            seq=index + 1,
            record=key,
            op=OpKind.UPSERT,
            payload=keyed[key],
            hlc=HLC(at_us, index, origin),
            actor=actor,
            fence=fence,
        )
        for index, key in enumerate(sorted(keyed))
    ]


def install_genesis(store: Store, entries: Sequence[OpEntry]) -> ReplayResult:
    """Apply a genesis log to ``store``. Idempotent and resumable.

    Refuses with :class:`~._errors.AdoptionRefusedError` when ``store``
    already holds rows but has never seen this genesis — that store got its
    data by some other route, and folding a genesis log into it would merge
    two datasets on recency without raising.

    Re-running is safe: an already-installed genesis is recognised and
    applied zero times, and a partially-installed one resumes at its cursor
    rather than restarting or erroring.
    """
    ordered = list(entries)
    if not ordered:
        return ReplayResult(source="", applied=0, cursor_before=0, cursor_after=0)

    origin = ordered[0].origin
    foreign = sorted({e.origin for e in ordered if e.origin != origin})
    if foreign:
        raise StoreError(
            f"A genesis log must carry ONE origin; this batch also contains "
            f"{foreign}. Sequence numbers are per-origin, so a mixed batch "
            "has no meaningful cursor. Build it with build_genesis()."
        )

    cursor = store.cursor(origin)
    if cursor == 0 and store.rows(include_hidden=True):
        raise AdoptionRefusedError(
            f"Refusing to install genesis {origin!r} into a store that "
            f"already holds rows and has never applied it. Those rows came "
            "from somewhere else — most likely replay from a peer that "
            "adopted already, in which case this store is ALREADY adopted "
            "and needs nothing.\n"
            "Installing anyway would not replace them: genesis ops are "
            "well-formed, so field-level merge would fold two unrelated "
            "datasets together on recency and report success.\n"
            "Remedy: if this store should hold the adopted data, let it "
            "arrive by sync() from a host that has the genesis. If it should "
            "be adopted directly, do it on an EMPTY store."
        )

    if cursor >= len(ordered):
        _check_same_genesis(store, ordered, cursor)
        return ReplayResult(
            source=origin,
            applied=0,
            cursor_before=cursor,
            cursor_after=cursor,
        )

    if cursor > 0:
        _check_same_genesis(store, ordered, cursor)

    return replay(store, origin, ordered[cursor:])


def _check_same_genesis(
    store: Store, ordered: Sequence[OpEntry], cursor: int
) -> None:
    """Verify the already-applied prefix is THIS genesis, not another one.

    Compares the entry at ``seq == cursor``. Without it, installing a
    DIFFERENT genesis onto a partially-installed store would resume from the
    cursor and splice two logs into one sequence space — contiguous,
    well-formed, and describing a history that never happened.

    One entry rather than the whole prefix: the check exists to catch a
    different artefact, and two distinct genesis logs over the same dataset
    differ in their stamps, so any single shared position separates them.
    """
    applied = store.changes_since(ordered[0].origin, cursor - 1, limit=1)
    if not applied:
        return
    expected = ordered[cursor - 1]
    found = applied[0]
    if found.record == expected.record and found.hlc == expected.hlc:
        return
    raise AdoptionRefusedError(
        f"Genesis {ordered[0].origin!r} is already partially installed in "
        f"this store at seq {cursor}, but the log offered does not match it: "
        f"stored {found.describe()} at {found.hlc.encode()}, offered "
        f"{expected.describe()} at {expected.hlc.encode()}.\n"
        "Resuming would splice two different genesis logs into one sequence "
        "space, producing a contiguous, well-formed history that never "
        "happened.\n"
        "Remedy: install the SAME artefact this store started with, or adopt "
        "into a fresh store under a new genesis_origin() stamp."
    )


def verify_adoption(
    store: Store,
    records: Iterable[Mapping[str, Any]],
    *,
    schema: "Schema | None" = None,
) -> list[str]:
    """Compare every source record against the store, FIELD BY FIELD.

    Returns one description per mismatch; empty means the adopted store
    reproduces the source exactly.

    Deliberately not a count comparison. Counts agreeing is the failure mode
    this fleet keeps paying for: on 2026-08-10 two card stores both reported
    3,707 rows while 7,646 bytes differed between them, and a count check
    would have shipped the loss. A row-and-field diff cannot agree for the
    wrong reason.
    """
    active = schema or store.schema
    problems: list[str] = []
    for record in records:
        key = record_key(active, record)
        row = store.get(
            tuple(record[name] for name in active.identity_fields),
            include_hidden=True,
        )
        if row is None:
            problems.append(f"{key}: absent from the store after adoption")
            continue
        for name, source_value in record.items():
            stored = row.values.get(name)
            if stored != source_value:
                problems.append(
                    f"{key}.{name}: source {source_value!r} != stored {stored!r}"
                )
    return problems

# EOF
