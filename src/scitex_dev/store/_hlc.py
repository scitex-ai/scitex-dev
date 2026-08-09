#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hybrid logical clock — the ordering authority for conflict resolution.

Why not bare wall-clock
-----------------------
Conflicts are resolved "by time", but *whose* time? Two hosts writing the
same record decide the winner by comparing timestamps, and unsynchronised
wall-clocks make that comparison lie: a host running two seconds fast wins
every race it enters, including races it causally lost. Worse, the
comparison is not even a total order — two writes can tie, and a tie in a
last-writer-wins merge means the outcome depends on iteration order.

A hybrid logical clock (Kulkarni et al., 2014) keeps a physical component
so timestamps stay human-meaningful and roughly track real time, plus a
logical counter that preserves causality when the physical component does
not advance. Every message received drags the local clock forward, so a
value that was observed can never be re-issued as "earlier".

The node id is the third component and it is not decoration: it makes the
order TOTAL. Without it two nodes can mint identical ``(wall, logical)``
pairs and the merge has no deterministic winner, so two replicas of the
same log converge to different states.

Drift guard
-----------
Standard HLC accepts any remote timestamp and jumps to it. That is a
permanent, unrecoverable poisoning vector: one write stamped a year ahead
drags the local clock a year ahead, and every honest local write loses
last-writer-wins until real time catches up. :class:`HybridLogicalClock`
refuses instead, bounding the damage to the batch that carried the bad
stamp. That is a deliberate divergence from the paper, and it is the
"fail fast, no silent fallback" rule applied to time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Final

from ._errors import ClockDriftError

__all__ = [
    "DEFAULT_MAX_DRIFT_S",
    "HLC",
    "HybridLogicalClock",
]

#: How far ahead of local physical time a remote stamp may be before it is
#: rejected. Generous enough for ordinary NTP skew and scheduling jitter,
#: far tighter than the "silently accept anything" default.
DEFAULT_MAX_DRIFT_S: Final[float] = 300.0

_US_PER_S: Final[int] = 1_000_000


@dataclass(frozen=True, order=False, slots=True)
class HLC:
    """One hybrid-logical timestamp.

    Ordered by ``(wall_us, logical, node)``. The tuple is a TOTAL order —
    two distinct nodes never compare equal — which is what makes
    last-writer-wins deterministic across replicas.
    """

    wall_us: int
    logical: int
    node: str

    def __post_init__(self) -> None:
        if self.wall_us < 0:
            raise ValueError(
                f"HLC.wall_us must be non-negative, got {self.wall_us!r}. "
                "A negative wall component means the source clock is before "
                "the epoch; fix the clock rather than the timestamp."
            )
        if self.logical < 0:
            raise ValueError(
                f"HLC.logical must be non-negative, got {self.logical!r}."
            )
        if not self.node:
            raise ValueError(
                "HLC.node must be a non-empty node id. Without it the order "
                "is not total and two replicas can pick different winners "
                "for the same conflict."
            )

    # -- ordering ---------------------------------------------------------
    @property
    def sort_key(self) -> tuple[int, int, str]:
        """The total-order key. Compare these, never the fields ad hoc."""
        return (self.wall_us, self.logical, self.node)

    def __lt__(self, other: "HLC") -> bool:
        return self.sort_key < other.sort_key

    def __le__(self, other: "HLC") -> bool:
        return self.sort_key <= other.sort_key

    def __gt__(self, other: "HLC") -> bool:
        return self.sort_key > other.sort_key

    def __ge__(self, other: "HLC") -> bool:
        return self.sort_key >= other.sort_key

    # -- serialisation ----------------------------------------------------
    def encode(self) -> str:
        """A sortable-per-node string form for logs and debugging."""
        return f"{self.wall_us}.{self.logical}.{self.node}"

    @classmethod
    def decode(cls, text: str) -> "HLC":
        """Inverse of :meth:`encode`."""
        parts = text.split(".", 2)
        if len(parts) != 3:
            raise ValueError(
                f"Malformed HLC {text!r}: expected 'wall_us.logical.node'. "
                "Produce these with HLC.encode(), not by string building."
            )
        wall_text, logical_text, node = parts
        try:
            return cls(int(wall_text), int(logical_text), node)
        except ValueError as exc:
            raise ValueError(
                f"Malformed HLC {text!r}: {exc}. Expected two integers then "
                "the node id."
            ) from None

    @property
    def wall_seconds(self) -> float:
        """The physical component in seconds, for human-facing output."""
        return self.wall_us / _US_PER_S


class HybridLogicalClock:
    """A per-node HLC. One instance per process that writes to a store.

    Not thread-safe by itself; the store holds it behind the same lock
    that serialises oplog appends, so every minted stamp is unique per
    node by construction.
    """

    def __init__(
        self,
        node: str,
        *,
        max_drift_s: float = DEFAULT_MAX_DRIFT_S,
        time_source: "callable[[], float] | None" = None,
    ) -> None:
        if not node:
            raise ValueError(
                "HybridLogicalClock requires a non-empty node id — it is the "
                "tie-breaker that makes the timestamp order total."
            )
        if max_drift_s <= 0:
            raise ValueError(
                f"max_drift_s must be positive, got {max_drift_s!r}. Use a "
                "large value to loosen the guard; zero would reject every "
                "remote stamp including correct ones."
            )
        self.node = node
        self.max_drift_s = max_drift_s
        self._time_source = time_source or time.time
        self._last = HLC(0, 0, node)

    # -- local time -------------------------------------------------------
    def now(self) -> HLC:
        """Mint the next local timestamp.

        Monotonic per node even if the physical clock steps backwards: the
        wall component never decreases, and the logical counter advances
        instead.
        """
        physical_us = int(self._time_source() * _US_PER_S)
        if physical_us > self._last.wall_us:
            self._last = HLC(physical_us, 0, self.node)
        else:
            self._last = HLC(self._last.wall_us, self._last.logical + 1, self.node)
        return self._last

    # -- remote time ------------------------------------------------------
    def observe(self, remote: HLC) -> HLC:
        """Absorb a remote timestamp and mint one that strictly follows it.

        Raises :class:`ClockDriftError` when ``remote`` is further ahead of
        local physical time than ``max_drift_s``, rather than jumping the
        local clock to it.
        """
        physical_us = int(self._time_source() * _US_PER_S)
        drift_s = (remote.wall_us - physical_us) / _US_PER_S
        if drift_s > self.max_drift_s:
            raise ClockDriftError(
                f"Remote HLC {remote.encode()} is {drift_s:.1f}s ahead of "
                f"local physical time on node {self.node!r}, exceeding the "
                f"{self.max_drift_s:.1f}s guard. Accepting it would advance "
                "this node's clock permanently and make every later local "
                "write lose last-writer-wins until real time catches up. "
                f"Fix the clock on node {remote.node!r} (check NTP), or pass "
                "a larger max_drift_s if this skew is genuinely expected."
            )

        wall_us = max(physical_us, self._last.wall_us, remote.wall_us)
        if wall_us == self._last.wall_us == remote.wall_us:
            logical = max(self._last.logical, remote.logical) + 1
        elif wall_us == self._last.wall_us:
            logical = self._last.logical + 1
        elif wall_us == remote.wall_us:
            logical = remote.logical + 1
        else:
            logical = 0

        self._last = HLC(wall_us, logical, self.node)
        return self._last

    @property
    def last(self) -> HLC:
        """The most recently minted timestamp (``wall_us == 0`` if none)."""
        return self._last

# EOF
