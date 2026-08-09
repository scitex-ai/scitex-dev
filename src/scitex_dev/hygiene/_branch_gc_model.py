#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data + vocabulary for the branch GC. No subprocess, no I/O.

The keep-reason strings are API, not debug text: they land in
``scitex-dev ecosystem prune-branches --json``, in the console report and
in the cron log's breakdown, which is what makes a pass auditable after
the fact ("31 kept: 22 not-landed, 6 too-young, 3 active-work") instead of
merely quiet ("31 kept").
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass

__all__ = [
    "DEFAULT_BRANCH_CAP",
    "DEFAULT_MIN_AGE_DAYS",
    "HARD_MIN_AGE_DAYS",
    "KEEP_ACTIVE_WORK",
    "KEEP_ACTIVE_WORK_UNKNOWN",
    "KEEP_AGE_UNKNOWN",
    "KEEP_CHECKED_OUT",
    "KEEP_DELETE_FAILED",
    "KEEP_DEFERRED_BY_LIMIT",
    "KEEP_MOVED_DURING_PASS",
    "KEEP_NOT_LANDED",
    "KEEP_LANDED_UNKNOWN",
    "KEEP_OPEN_PR",
    "KEEP_PR_STATE_UNKNOWN",
    "KEEP_PROTECTED",
    "KEEP_TOO_YOUNG",
    "LANDED_BY_ANCESTOR",
    "LANDED_BY_MERGED_PR",
    "LANDED_BY_PATCH_EQUIVALENCE",
    "MERGE_BASES",
    "PROTECTED_BRANCH_GLOBS",
    "PROTECTED_BRANCH_NAMES",
    "SHA_DELETABLE_LANDED_SOURCES",
    "BranchGcOutcome",
    "BranchInfo",
    "BranchVerdict",
    "Landed",
    "RepoBranchGcResult",
    "clamp_min_age_days",
    "exit_code_for",
    "is_protected_name",
]

#: Used when the repo's ``cleanup.branches`` block omits ``min-age-days``.
DEFAULT_MIN_AGE_DAYS = 30.0

#: The floor no configuration may lower. A value below this is CLAMPED UP,
#: never honoured. This constant is the whole reason this primitive exists:
#: the 2026-08-08 incident destroyed 7 branches that were minutes old, and
#: ANY age floor at all would have saved every one of them. 14 days makes it
#: structurally impossible for a same-day sweep to reach same-session work
#: even if every other leg of the predicate were simultaneously wrong.
HARD_MIN_AGE_DAYS = 14.0

#: Local branches above this count make a repo DEGRADED in the report. It is
#: an ALARM THRESHOLD, never a deletion target: the predicate is not relaxed
#: to hit a number, and nothing is truncated to satisfy it.
DEFAULT_BRANCH_CAP = 40

#: Bases a branch may have landed on, checked in order. A base that does not
#: exist in the repo is SKIPPED, not treated as a failure — but a base we
#: never read also never contributes to a definite "not landed".
MERGE_BASES = ("develop", "main")

#: Never deletable, at any config, on any repo.
PROTECTED_BRANCH_NAMES = frozenset({"main", "master", "develop"})

#: Glob-protected families. ``release/*`` is here because the pre-existing
#: ``PROTECTED_BRANCHES`` set in ``_cmds/_sync_helpers.py`` omits it.
PROTECTED_BRANCH_GLOBS = ("release/*",)

KEEP_NOT_LANDED = "not-landed"
KEEP_LANDED_UNKNOWN = "landed-unknown"
KEEP_TOO_YOUNG = "too-young"
KEEP_AGE_UNKNOWN = "age-unknown"
KEEP_CHECKED_OUT = "checked-out"
KEEP_PROTECTED = "protected"
KEEP_OPEN_PR = "open-pr"
KEEP_PR_STATE_UNKNOWN = "pr-state-unknown"
KEEP_ACTIVE_WORK = "active-work"
KEEP_ACTIVE_WORK_UNKNOWN = "active-work-unknown"
KEEP_MOVED_DURING_PASS = "moved-during-pass"
KEEP_DELETE_FAILED = "delete-failed"
KEEP_DEFERRED_BY_LIMIT = "deferred-by-limit"

LANDED_BY_ANCESTOR = "ancestor"
LANDED_BY_PATCH_EQUIVALENCE = "patch-equivalent"
LANDED_BY_MERGED_PR = "merged-pr"

#: Landing proofs strong enough to justify the compare-and-delete fallback
#: when ``git branch -d`` refuses. Both are PATCH-LEVEL proofs that the work
#: is present on a base; ``-d`` only understands ANCESTRY, so it refuses a
#: squash-merge and a rebase-landing alike. The fallback is still strictly
#: safer than ``-D``: it names the exact SHA and git refuses if the ref moved.
SHA_DELETABLE_LANDED_SOURCES = (LANDED_BY_MERGED_PR, LANDED_BY_PATCH_EQUIVALENCE)


def is_protected_name(name: str, extra_globs: tuple[str, ...] = ()) -> bool:
    """True iff ``name`` is a never-delete branch name.

    Built-in protection is not configurable — ``extra_globs`` only ever
    ADDS to it, so a repo config can widen the shield and never narrow it.
    """
    if name in PROTECTED_BRANCH_NAMES:
        return True
    for pattern in tuple(PROTECTED_BRANCH_GLOBS) + tuple(extra_globs):
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def clamp_min_age_days(value: float | None) -> float:
    """Return the effective age floor: never below :data:`HARD_MIN_AGE_DAYS`.

    ``None`` / non-numeric / negative all resolve to
    :data:`DEFAULT_MIN_AGE_DAYS`, and every result is then clamped UP. The
    clamp is one-directional on purpose: config may make the sweep more
    conservative, never less.
    """
    if value is None:
        value = DEFAULT_MIN_AGE_DAYS
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = DEFAULT_MIN_AGE_DAYS
    if numeric != numeric or numeric < 0:  # NaN or negative
        numeric = DEFAULT_MIN_AGE_DAYS
    return max(numeric, HARD_MIN_AGE_DAYS)


@dataclass(frozen=True)
class BranchInfo:
    """One ``refs/heads/*`` entry, as reported by git."""

    name: str
    sha: str = ""


@dataclass(frozen=True)
class Landed:
    """Leg-1 outcome: the verdict AND which source proved it."""

    value: bool | None = None
    source: str = ""
    reason: str = ""


@dataclass(frozen=True)
class BranchVerdict:
    """What we decided about ONE branch, and why — never just a bool."""

    name: str
    sha: str = ""
    keep_reasons: tuple[str, ...] = ()
    landed_source: str = ""
    deleted: bool = False
    delete_error: str = ""

    @property
    def deletable(self) -> bool:
        """True iff EVERY leg passed. One reason is enough to keep."""
        return not self.keep_reasons

    def with_reason(self, reason: str) -> "BranchVerdict":
        """Return a copy carrying one more keep reason (frozen-safe)."""
        return BranchVerdict(
            name=self.name,
            sha=self.sha,
            keep_reasons=self.keep_reasons + (reason,),
            landed_source=self.landed_source,
            deleted=self.deleted,
            delete_error=self.delete_error,
        )

    def to_dict(self) -> dict:
        return {
            "branch": self.name,
            "sha": self.sha[:12],
            "deletable": self.deletable,
            "keep_reasons": list(self.keep_reasons),
            "landed_source": self.landed_source,
            "deleted": self.deleted,
            "delete_error": self.delete_error,
        }


@dataclass(frozen=True)
class RepoBranchGcResult:
    """One repo's pass: config state, every verdict, the backup, the damage."""

    repo: str
    enabled: bool = False
    applied: bool = False
    cap: int = DEFAULT_BRANCH_CAP
    min_age_days: float = DEFAULT_MIN_AGE_DAYS
    verdicts: tuple[BranchVerdict, ...] = ()
    config_source: str | None = None
    config_error: str | None = None
    #: Set when the pass STOPPED before deleting anything it otherwise would
    #: have. Never rendered as a clean pass.
    abort_reason: str = ""
    backup_dir: str = ""
    bundle_path: str = ""
    restore_command: str = ""
    prune_detail: str = ""
    error: str = ""

    @property
    def unreadable(self) -> bool:
        """The repo could not be READ — UNKNOWN, never "no branches"."""
        return bool(self.error)

    @property
    def deleted(self) -> tuple[BranchVerdict, ...]:
        return tuple(v for v in self.verdicts if v.deleted)

    @property
    def kept(self) -> tuple[BranchVerdict, ...]:
        return tuple(v for v in self.verdicts if not v.deleted)

    @property
    def candidates(self) -> tuple[BranchVerdict, ...]:
        """Branches that passed all five legs (deleted or merely reported)."""
        return tuple(v for v in self.verdicts if v.deletable or v.deleted)

    @property
    def count_before(self) -> int:
        return len(self.verdicts)

    @property
    def count_after(self) -> int:
        return self.count_before - len(self.deleted)

    @property
    def exceeds_cap(self) -> bool:
        return self.count_after > self.cap

    @property
    def keep_reason_breakdown(self) -> dict[str, int]:
        """``{"not-landed": 22, "too-young": 6}`` — WHY survivors survived."""
        counts: dict[str, int] = {}
        for verdict in self.kept:
            for reason in verdict.keep_reasons:
                counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "enabled": self.enabled,
            "applied": self.applied,
            "cap": self.cap,
            "min_age_days": self.min_age_days,
            "config_source": self.config_source,
            "config_error": self.config_error,
            "abort_reason": self.abort_reason,
            "error": self.error,
            "count_before": self.count_before,
            "count_after": self.count_after,
            "exceeds_cap": self.exceeds_cap,
            "deleted": [v.name for v in self.deleted],
            "candidates": [v.name for v in self.candidates],
            "keep_reasons": self.keep_reason_breakdown,
            "backup_dir": self.backup_dir,
            "bundle": self.bundle_path,
            "restore_command": self.restore_command,
            "prune": self.prune_detail,
            "branches": [v.to_dict() for v in self.verdicts],
        }


@dataclass(frozen=True)
class BranchGcOutcome:
    """The whole pass across every repo — so a sweep is never silent."""

    results: tuple[RepoBranchGcResult, ...] = ()

    @property
    def deleted_count(self) -> int:
        return sum(len(r.deleted) for r in self.results)

    @property
    def kept_count(self) -> int:
        return sum(len(r.kept) for r in self.results)

    @property
    def candidate_count(self) -> int:
        return sum(len(r.candidates) for r in self.results)

    @property
    def aborted(self) -> tuple[RepoBranchGcResult, ...]:
        return tuple(r for r in self.results if r.abort_reason)

    @property
    def unreadable(self) -> tuple[RepoBranchGcResult, ...]:
        return tuple(r for r in self.results if r.unreadable)

    @property
    def over_cap(self) -> tuple[RepoBranchGcResult, ...]:
        return tuple(r for r in self.results if r.exceeds_cap)

    def summary_line(self) -> str:
        parts = [
            f"{len(self.results)} repo(s)",
            f"{self.deleted_count} deleted",
            f"{self.candidate_count} candidate(s)",
            f"{self.kept_count} kept",
        ]
        if self.over_cap:
            parts.append(f"{len(self.over_cap)} OVER CAP")
        if self.aborted:
            parts.append(f"{len(self.aborted)} ABORTED")
        if self.unreadable:
            parts.append(f"{len(self.unreadable)} UNREADABLE")
        return ", ".join(parts)


def exit_code_for(outcome: BranchGcOutcome) -> int:
    """Worst verdict wins — a sweep never hides one bad repo behind good ones.

    0 = every repo read, none over cap, nothing aborted. 1 = a known-bad
    (over cap, or a pass that aborted before deleting). 2 = at least one
    repo could not be READ, which OUTRANKS 1: an unknown is worse than a
    known-bad, because it is a known-bad you cannot see.
    """
    if outcome.unreadable:
        return 2
    return 1 if (outcome.over_cap or outcome.aborted) else 0


# EOF
