#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Divergence detection — proving two stores minted different histories.

What makes this different from every reconciler that has hurt this fleet
-----------------------------------------------------------------------
**Absence is never evidence here.** The question asked is not "what does
each side HAVE?" but "where do the two logs, at a position BOTH sides
filled, disagree?"

That distinction is the whole design. Set-difference reconciliation replaced
2,159 live rows with a 5-row temporary document on 2026-07-19/21 by reading
"present here, missing there" as a deletion. This module cannot make that
inference: a peer that is merely BEHIND has no op at the sequence in
question, so there is nothing to disagree with and nothing is reported.
Being behind is normal — it is what a cursor is for — and is reported
separately, as a number, under a different name.

The proof
---------
``seq`` is minted by the ORIGIN — the node that accepted the write — and is
gapless per origin. So one origin cannot legitimately produce two DIFFERENT
ops at one sequence number. If both stores hold an op at ``(origin, seq)``
and the two ops differ, then two writers were both numbering as that origin,
each believing it was the only one. That is a fork, and it is proven rather
than inferred.

This is the log-side counterpart to :mod:`._identity`, and both are needed:

* identity catches a fork BEFORE any divergence exists — two separately
  initialised instances answering to one ``store_uuid`` — but it needs the
  serving system to name itself, which a restricted Postgres role will not;
* the log catches a fork that identity cannot see (a physical copy carries
  its instance id with it) but only AFTER both halves have written.

Neither subsumes the other. A check that only did one would report healthy
in exactly the cases the other exists for.

Why the search is a bisection
-----------------------------
Ops are immutable once written, so a fork produces an agreeing PREFIX and
then permanent disagreement: agreement is monotone in ``seq``, which is what
licenses a bisection over a log that may hold millions of entries. The
sequence reported is therefore the earliest disagreement — the fork point.

If disagreement were somehow NOT monotone (a store whose log had been edited
in place, which nothing in this primitive can do), the bisection would still
return a real disagreeing pair — a true positive — but not necessarily the
earliest one. Stated because a reader deserves to know which half of the
claim is structural and which rests on the append-only guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._errors import StoreDivergedError
from ._identity import IdentityVerdict, StoreIdentity, compare_identity
from ._oplog import OpEntry

__all__ = [
    "DivergenceReport",
    "ForkPoint",
    "detect_divergence",
]


def _fingerprint(entry: OpEntry) -> tuple[Any, ...]:
    """The part of an op two copies of one log must agree on exactly.

    ``fence`` is excluded deliberately: it was added as an additive column
    with a default, so a store written before the migration reads it back
    as ``FENCE_UNKNOWN`` while a newer copy of the SAME op may carry a real
    value. Including it would report every pre-migration store as forked
    from its own replica — a false fork, which is worse than no check,
    because a fork alarm that fires wrongly trains its reader to ignore the
    one that does not.
    """
    return (entry.record, entry.op.value, entry.payload_json(), entry.hlc.encode())


@dataclass(frozen=True, slots=True)
class ForkPoint:
    """One proven disagreement: both logs filled ``(origin, seq)`` differently."""

    origin: str
    seq: int
    ours: OpEntry
    theirs: OpEntry

    def describe(self) -> str:
        """One line naming the sequence and both versions of it."""
        return (
            f"{self.origin}#{self.seq}: here {self.ours.describe()} "
            f"@{self.ours.hlc.encode()} | there {self.theirs.describe()} "
            f"@{self.theirs.hlc.encode()}"
        )


@dataclass(frozen=True, slots=True)
class DivergenceReport:
    """Everything one comparison learned. Every signal its own field.

    ``forks`` is the only field that PROVES divergence. ``behind`` and
    ``ahead`` are ordinary replication lag and are carried separately so
    that a caller cannot accidentally treat lag as damage — which is the
    inference this whole module exists to make unavailable.
    """

    local_node: str
    remote_node: str
    local_identity: "StoreIdentity | None"
    remote_identity: "StoreIdentity | None"
    forks: tuple[ForkPoint, ...] = ()
    behind: "dict[str, int] | None" = None
    ahead: "dict[str, int] | None" = None

    @property
    def identity_verdict(self) -> IdentityVerdict:
        """How the two identities compare, or UNKNOWN when either is absent."""
        if self.local_identity is None or self.remote_identity is None:
            return IdentityVerdict.UNKNOWN
        return compare_identity(self.local_identity, self.remote_identity)

    @property
    def diverged(self) -> bool:
        """Whether divergence is PROVEN.

        True only when a fork point was found or the instances differ under
        one lineage. Deliberately NOT true for lag, and deliberately not
        true for UNKNOWN: "we could not tell" is reported by
        :attr:`certified_same`, which is a different question.
        """
        return bool(self.forks) or self.identity_verdict is IdentityVerdict.FORK

    @property
    def certified_same(self) -> bool:
        """Whether these are PROVEN to be one store with one history."""
        return (
            self.identity_verdict is IdentityVerdict.SAME and not self.forks
        )

    def describe(self) -> str:
        """A short report, safe to put in a log line or a card note."""
        head = (
            f"{self.local_node} vs {self.remote_node}: "
            f"identity={self.identity_verdict.value}"
        )
        if self.forks:
            head += f", {len(self.forks)} fork point(s)"
        for gap, label in ((self.behind, "behind"), (self.ahead, "ahead")):
            if gap:
                head += f", {label}={gap}"
        if not self.forks and not self.diverged:
            return head
        return "\n".join([head, *(f"  {f.describe()}" for f in self.forks)])

    def raise_if_diverged(self, *, context: str = "") -> None:
        """Refuse to continue when divergence is proven. The loud half.

        ``context`` is prepended verbatim — what the caller was about to do
        is far more useful in a traceback than the bare fact of a fork.
        """
        if not self.diverged:
            return
        prefix = f"{context}: " if context else ""
        detail = "\n".join(f"  {f.describe()}" for f in self.forks)
        raise StoreDivergedError(
            f"{prefix}{self.local_node} and {self.remote_node} have DIVERGED "
            "— they share a lineage and hold different histories under it.\n"
            f"{self.describe()}\n"
            + (f"\nProven at:\n{detail}\n" if detail else "")
            + "\n"
            "Each side holds writes the other has never seen, and neither "
            "side errors: this is the 2026-08-11 shape, where a peer could "
            "not close its own card, a card read 'blocked' on one side and "
            "'cancelled' on the other, and an inbox notification redelivered "
            "in a loop while poll_notifications truthfully answered UNSEEN 0 "
            "— about the other store.\n"
            "\n"
            "Remedy: reconcile by REPLAY, in both directions "
            "(scitex_dev.store.sync(a, b) then sync(b, a)). Do NOT copy rows "
            "and do NOT compare what each side HAS: absence in one is not "
            "deletion in the other, and treating it as such destroyed 2,159 "
            "rows on 2026-07-19/21."
        )


def _op_at(store: Any, origin: str, seq: int) -> "OpEntry | None":
    """The single op ``origin`` minted at ``seq``, or None if absent."""
    if seq < 1:
        return None
    found = store.changes_since(origin, seq - 1, limit=1)
    if not found or found[0].seq != seq:
        return None
    return found[0]


def _first_disagreement(
    local: Any, remote: Any, origin: str, overlap: int
) -> "ForkPoint | None":
    """Bisect ``1..overlap`` for the earliest differing op, or None.

    Costs ``O(log n)`` op reads instead of ``n``: on a 3,712-op adoption
    that is twelve reads rather than thousands, which is what makes running
    this on every peer contact affordable rather than a batch job nobody
    schedules.
    """
    if overlap < 1:
        return None

    last = _op_at(local, origin, overlap)
    other = _op_at(remote, origin, overlap)
    if last is None or other is None:
        # One side has a hole where the other has an op. Not a fork by this
        # module's definition and NOT reported as one — a hole is either lag
        # mid-write or a damaged log, and both need a different remedy than
        # reconciliation. assert_contiguous is the check that owns holes.
        return None
    if _fingerprint(last) == _fingerprint(other):
        return None

    low, high = 1, overlap  # invariant: disagreement exists at `high`
    while low < high:
        middle = (low + high) // 2
        ours = _op_at(local, origin, middle)
        theirs = _op_at(remote, origin, middle)
        if ours is None or theirs is None or _fingerprint(ours) != _fingerprint(theirs):
            high = middle
        else:
            low = middle + 1

    ours = _op_at(local, origin, low)
    theirs = _op_at(remote, origin, low)
    if ours is None or theirs is None:
        return None
    return ForkPoint(origin=origin, seq=low, ours=ours, theirs=theirs)


def detect_divergence(local: Any, remote: Any) -> DivergenceReport:
    """Compare two open stores. Reads only; changes nothing on either side.

    Answers three questions in one pass, and keeps them separate in the
    result:

    1. do the two identities agree (:mod:`._identity`)?
    2. is there a position both logs filled DIFFERENTLY (a proven fork)?
    3. how far is each behind the other (ordinary lag)?

    Only (1) and (2) can mean damage. (3) is what replication is for, and
    conflating it with the others is the mistake that makes a healthy,
    catching-up peer look like a corrupted one.

    Identity is read defensively: a store that cannot report one (an older
    store predating the identity table, or a role without rights to read
    the instance id) yields ``None`` and the verdict falls to UNKNOWN,
    rather than the whole comparison failing. The log check still runs, and
    on a store with history it is the stronger of the two.
    """
    local_identity = _identity_of(local)
    remote_identity = _identity_of(remote)

    local_origins = local.origins()
    remote_origins = remote.origins()

    forks: list[ForkPoint] = []
    for origin in sorted(set(local_origins) & set(remote_origins)):
        overlap = min(local_origins[origin], remote_origins[origin])
        fork = _first_disagreement(local, remote, origin, overlap)
        if fork is not None:
            forks.append(fork)

    behind = {
        origin: highest - local.cursor(origin)
        for origin, highest in remote_origins.items()
        if origin != local.node and highest - local.cursor(origin) > 0
    }
    ahead = {
        origin: highest - remote.cursor(origin)
        for origin, highest in local_origins.items()
        if origin != remote.node and highest - remote.cursor(origin) > 0
    }

    return DivergenceReport(
        local_node=local.node,
        remote_node=remote.node,
        local_identity=local_identity,
        remote_identity=remote_identity,
        forks=tuple(forks),
        behind=behind,
        ahead=ahead,
    )


def _identity_of(store: Any) -> "StoreIdentity | None":
    """``store.identity``, or None when the store cannot report one.

    Swallowing the error is right HERE and nowhere else: this function's
    caller reports a verdict of UNKNOWN, which is itself a refusal to
    certify. The absence is carried forward as a value rather than hidden.
    """
    try:
        return store.identity
    except Exception:
        return None

# EOF
