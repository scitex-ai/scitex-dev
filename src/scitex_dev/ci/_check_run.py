#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/ci/_check_run.py
"""One check run, and whether it describes the commit we care about.

The states are split into named sets rather than compared inline because
each set answers a different question, and folding any two of them together
is a known way to produce a green that means nothing:

- PENDING is not a verdict yet — the answer is knowable, just not known.
- SKIPPED is not a pass — CI reached the job and chose not to run it.
- A run whose SHA differs from the head describes DIFFERENT CODE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = ["CheckRun"]

#: States GitHub reports for a check that has not finished. Treated as
#: NOT READY rather than unknown: the answer is knowable, it just is not
#: known YET, and merging now would merge on an unfinished gate.
PENDING_STATES: Final[frozenset[str]] = frozenset(
    {"QUEUED", "IN_PROGRESS", "PENDING", "WAITING", "REQUESTED", "ACTION_REQUIRED"}
)

#: States that mean the check ran and did not pass.
FAILING_STATES: Final[frozenset[str]] = frozenset(
    {"FAILURE", "TIMED_OUT", "CANCELLED", "STALE", "STARTUP_FAILURE", "ERROR"}
)

#: A skipped check RAN in the sense that CI reached it and decided not to
#: execute it. That is legitimate (a conditional job), which is exactly why
#: it must never be folded into the pass total: "skipped" and "passed" are
#: different facts and only one of them is evidence the code works.
SKIPPED_STATES: Final[frozenset[str]] = frozenset({"SKIPPED", "NEUTRAL"})


@dataclass(frozen=True, slots=True)
class CheckRun:
    """One check, and whether it describes the commit we care about."""

    name: str
    state: str
    #: The commit this run actually executed against. ``None`` when the API
    #: did not report one — which is itself a reason to distrust the run.
    head_sha: "str | None"
    #: True when ``head_sha`` differs from the PR's current head. A stale
    #: run's verdict is about different code.
    stale: bool
    #: False only when the check is absent for this head — distinct from
    #: having run and failed.
    ran: bool
    #: True when a LATER run of the same check name exists on this same head
    #: — a re-run, or a second workflow run of identical code. Superseded
    #: attempts are reported but do not decide readiness.
    #:
    #: WHY, measured 2026-08-09: `pytest-matrix-py3.12` died mid-step at
    #: 20:33 (infrastructure, not a test) and a second run of the SAME commit
    #: passed at 20:44. Both rows live on the same head SHA. Counting every
    #: row meant the dead attempt poisoned the verdict permanently — no
    #: re-run could ever clear it. A tool that cannot be un-failed by a
    #: successful re-run is broken precisely where re-runs exist.
    superseded: bool = False

    @property
    def passed(self) -> bool:
        return self.ran and not self.stale and self.state.upper() == "SUCCESS"

    @property
    def pending(self) -> bool:
        return self.state.upper() in PENDING_STATES

    @property
    def failed(self) -> bool:
        return self.state.upper() in FAILING_STATES

    @property
    def skipped(self) -> bool:
        return self.state.upper() in SKIPPED_STATES

    def describe(self) -> str:
        """One line, naming what is wrong and which commit it refers to."""
        if self.superseded:
            return (
                f"{self.name}: {self.state} on an EARLIER attempt, superseded "
                "by a later run of the same check on this head"
            )
        if not self.ran:
            return f"{self.name}: NEVER RAN on this head"
        if self.stale:
            short = (self.head_sha or "?")[:7]
            return (
                f"{self.name}: {self.state} but ran on {short}, "
                "NOT the current head — inherited verdict, describes other code"
            )
        if self.pending:
            return f"{self.name}: {self.state} — still running, not a verdict yet"
        if self.failed:
            return f"{self.name}: {self.state}"
        if self.skipped:
            return f"{self.name}: {self.state} — did not execute (not a pass)"
        return f"{self.name}: {self.state}"


# EOF
