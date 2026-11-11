#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vocabulary for the ``disk`` hygiene sweep.

One host, one pass. The sweep reclaims three kinds of space, each with
its own failure mode, so each gets its own candidate kind and its own
safety legs in :mod:`._disk_guard_predicate`:

- ``SIF_SUPERSEDED`` — dated ``<family>-YYYY-*.sif`` builds under the
  agent-container ``containers/`` tree that a newer build (or the live
  ``<family>.sif`` symlink) superseded. Failure mode: a live Apptainer
  runtime still has the file open — deleting it breaks the agent's next
  restart. (Observed 2026-10-27 on scitex-compute-03: 22 runtimes pinned
  to a superseded base SIF while the symlink pointed two builds newer.)
- ``CI_TMPDIR`` — stale ``/tmp/ci-*`` runner leftovers. Failure mode: a
  job is still writing into it. Age + open-file check.
- ``BUILD_CACHE`` — Docker build cache, which on CI/build hosts grows
  without bound (observed 146 GB reclaimable on scitex-compute-03 while
  named images totalled ~5 GB). Failure mode: none for running
  containers — cache is never a runtime dependency — but pruning under a
  threshold is pointless churn, so cache is touched ONLY at or above the
  configured use threshold, and never while a build is in flight.

The asymmetry from the package docstring holds here too: a false KEEP
leaves garbage on disk (the guard runs again in 6h). A false DELETE can
break a live agent or a running build. We pick the full disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "DEFAULT_MIN_AGE_DAYS",
    "DEFAULT_SIF_KEEP_NEWEST",
    "DEFAULT_THRESHOLD_PCT",
    "HARD_MIN_AGE_DAYS",
    "HARD_MIN_SIF_KEEP",
    "MAX_THRESHOLD_PCT",
    "MIN_THRESHOLD_PCT",
    "DiskCandidateKind",
    "DiskGuardOutcome",
    "DiskVerdict",
    "HostSweepResult",
    "clamp_min_age_days",
    "clamp_sif_keep_newest",
    "clamp_threshold_pct",
    "disk_exit_code_for",
]

#: Below this use% the build cache is left alone even when armed — cache
#: is useful, and pruning it is churn, not hygiene.
DEFAULT_THRESHOLD_PCT = 88
#: Clamp band for the threshold: below 50 it would prune a healthy host,
#: at/above 100 it could never fire.
MIN_THRESHOLD_PCT = 50
MAX_THRESHOLD_PCT = 99

#: Stale /tmp runner dirs must be this old before they are even candidates.
DEFAULT_MIN_AGE_DAYS = 2.0
#: No config can lower the age floor below this. Two days is already
#: aggressive for CI leftovers; one more incident does not get to invent
#: zero.
HARD_MIN_AGE_DAYS = 2.0

#: Per SIF family, that many newest dated builds are always kept, plus the
#: live symlink target and anything held open — whichever keeps more.
DEFAULT_SIF_KEEP_NEWEST = 2
HARD_MIN_SIF_KEEP = 1


def clamp_threshold_pct(raw: object) -> int:
    """Clamp the threshold into [50, 99]; garbage reads as the default."""
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD_PCT
    return max(MIN_THRESHOLD_PCT, min(MAX_THRESHOLD_PCT, value))


def clamp_min_age_days(raw: object) -> float:
    """Clamp the age floor UP to the hard minimum; garbage is the default."""
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_MIN_AGE_DAYS
    return max(HARD_MIN_AGE_DAYS, value)


def clamp_sif_keep_newest(raw: object) -> int:
    """Clamp the per-family keep count UP to the hard minimum of 1."""
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_SIF_KEEP_NEWEST
    return max(HARD_MIN_SIF_KEEP, value)


class DiskCandidateKind(str, Enum):
    SIF_SUPERSEDED = "sif-superseded"
    CI_TMPDIR = "ci-tmpdir"
    BUILD_CACHE = "build-cache"


@dataclass(frozen=True)
class DiskVerdict:
    """One candidate, one decision. KEEP carries the leg that kept it."""

    path: str
    kind: DiskCandidateKind
    size_bytes: int
    action: str  # "delete" | "keep"
    reason: str
    deleted: bool = False

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "size_bytes": self.size_bytes,
            "action": self.action,
            "reason": self.reason,
            "deleted": self.deleted,
        }


@dataclass
class HostSweepResult:
    """Everything one pass over one host decided and did."""

    host: str = ""
    enabled: bool = False
    config_error: str | None = None
    use_before_pct: float | None = None
    use_after_pct: float | None = None
    threshold_pct: int = DEFAULT_THRESHOLD_PCT
    candidates: tuple[DiskVerdict, ...] = ()
    aborted: str | None = None

    @property
    def deleted(self) -> tuple[DiskVerdict, ...]:
        return tuple(v for v in self.candidates if v.deleted)

    @property
    def kept(self) -> tuple[DiskVerdict, ...]:
        return tuple(v for v in self.candidates if not v.deleted)

    @property
    def freed_bytes(self) -> int:
        return sum(v.size_bytes for v in self.deleted)

    @property
    def keep_reason_breakdown(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for verdict in self.kept:
            counts[verdict.reason] = counts.get(verdict.reason, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "enabled": self.enabled,
            "config_error": self.config_error,
            "use_before_pct": self.use_before_pct,
            "use_after_pct": self.use_after_pct,
            "threshold_pct": self.threshold_pct,
            "freed_bytes": self.freed_bytes,
            "aborted": self.aborted,
            "candidates": [v.to_dict() for v in self.candidates],
        }

    def summary_line(self) -> str:
        if self.aborted:
            return f"disk-guard: ABORTED ({self.aborted})"
        if not self.enabled:
            return "disk-guard: off (cleanup.disk.enabled not literally true)"
        return (
            f"disk-guard: {len(self.deleted)} deleted "
            f"({self.freed_bytes} B freed), {len(self.kept)} kept; "
            f"use {self.use_before_pct}% -> {self.use_after_pct}%"
        )


@dataclass
class DiskGuardOutcome:
    results: tuple[HostSweepResult, ...] = ()
    error: str | None = None

    @property
    def deleted_count(self) -> int:
        return sum(len(r.deleted) for r in self.results)

    @property
    def aborted(self) -> tuple[HostSweepResult, ...]:
        return tuple(r for r in self.results if r.aborted)

    def summary_line(self) -> str:
        if self.error:
            return f"disk-guard: FAILED ({self.error})"
        return "; ".join(r.summary_line() for r in self.results)


def disk_exit_code_for(outcome: DiskGuardOutcome) -> int:
    """0 = pass ran everywhere. 1 = a pass aborted. 2 = unreadable/failed.

    Mirrors branch-gc's polarity: an unknown (could not even measure the
    host) outranks a known-bad (measured, aborted before deleting).
    """
    if outcome.error:
        return 2
    return 1 if outcome.aborted else 0


# EOF
