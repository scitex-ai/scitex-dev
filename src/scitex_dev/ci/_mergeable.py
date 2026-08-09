#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/ci/_mergeable.py
"""Is this pull request ACTUALLY mergeable? Answered per check, per commit.

Why this exists
---------------
Three failures on 2026-08-09, all of them a green that meant nothing:

1. Two agents reported branches green from LOCAL test runs; CI disagreed on
   every one. A local run is evidence about a container, not about the code.
2. An agent read a PR's checks and saw seven SUCCESS — from runs a week old,
   describing a commit that was not the PR's head. GitHub shows those runs
   on the PR page and does not tell you they are stale.
3. The same read came from the WRONG REPOSITORY: two repos in this fleet
   each had a ``#521``. A bare PR number is not an identifier here.

Each is the same shape — a signal that looks like a verdict about the
current code and is not. This module answers the question in a form that
cannot be misread, and :func:`readiness` exits non-zero so a script can
gate on it instead of a human squinting at a summary line.

What it refuses to do
---------------------
**Never trusts the summary count.** ``gh pr checks`` prints a rolled-up
line, and SKIPPING rows fold into the pass total — so "8 passed" can hide a
required check that never ran. Only per-check state is read.

**Never accepts an inherited green.** Every check run carries the SHA it
ran against. Any run whose SHA differs from the PR's current head is
reported as STALE and blocks readiness, because it describes different code.

**Never collapses "unknown" into "no", or into "yes".** A missing answer is
its own state. Deciding a PR is unmergeable because the API was unreachable
would train people to ignore the tool; deciding it is mergeable would ship
the bug. Both are wrong, so neither is returned.

**Never reports "never ran" as "failed".** They need different fixes: a
failure means read the log, an absent run means find out why CI did not
trigger. Collapsing them sends the reader to the wrong place.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Sequence

__all__ = [
    "CheckRun",
    "MergeReadiness",
    "Readiness",
    "EXIT_READY",
    "EXIT_NOT_READY",
    "EXIT_UNKNOWN",
    "EXIT_USAGE",
    "readiness",
]

#: Exit codes. Declared, documented, and distinct — a caller must be able to
#: tell "no" from "I could not tell", because those warrant different
#: actions. 0/1 keep their conventional meanings; the domain answers get
#: their own codes rather than overloading a generic failure.
EXIT_READY: Final[int] = 0
EXIT_USAGE: Final[int] = 1
EXIT_NOT_READY: Final[int] = 2
EXIT_UNKNOWN: Final[int] = 3

#: States GitHub reports for a check that has not finished. Treated as
#: NOT READY rather than unknown: the answer is knowable, it just is not
#: known YET, and merging now would merge on an unfinished gate.
_PENDING_STATES: Final[frozenset[str]] = frozenset(
    {"QUEUED", "IN_PROGRESS", "PENDING", "WAITING", "REQUESTED", "ACTION_REQUIRED"}
)

#: States that mean the check ran and did not pass.
_FAILING_STATES: Final[frozenset[str]] = frozenset(
    {"FAILURE", "TIMED_OUT", "CANCELLED", "STALE", "STARTUP_FAILURE", "ERROR"}
)

#: A skipped check RAN in the sense that CI reached it and decided not to
#: execute it. That is legitimate (a conditional job), which is exactly why
#: it must never be folded into the pass total: "skipped" and "passed" are
#: different facts and only one of them is evidence the code works.
_SKIPPED_STATES: Final[frozenset[str]] = frozenset({"SKIPPED", "NEUTRAL"})


class Readiness(str, Enum):
    """The three-valued answer. Never collapsed."""

    #: Every check that ran belongs to the current head and passed.
    READY = "ready"
    #: A definite no, with at least one reason naming a specific check.
    NOT_READY = "not-ready"
    #: The question could not be answered. NOT a synonym for "no".
    CANNOT_DETERMINE = "cannot-determine"


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

    @property
    def passed(self) -> bool:
        return self.ran and not self.stale and self.state.upper() == "SUCCESS"

    @property
    def pending(self) -> bool:
        return self.state.upper() in _PENDING_STATES

    @property
    def failed(self) -> bool:
        return self.state.upper() in _FAILING_STATES

    @property
    def skipped(self) -> bool:
        return self.state.upper() in _SKIPPED_STATES

    def describe(self) -> str:
        """One line, naming what is wrong and which commit it refers to."""
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


@dataclass(frozen=True, slots=True)
class MergeReadiness:
    """The same shape every time, whatever the answer.

    A caller never has to guess which field exists on this call. Validated
    where it is built, so a malformed verdict fails here rather than three
    layers downstream in whatever decided to merge.
    """

    readiness: Readiness
    #: Fully qualified — ``owner/repo#N``. A bare number is ambiguous across
    #: this fleet's repositories and has already been misread once.
    pr: str
    head_sha: "str | None"
    reasons: tuple[str, ...] = field(default_factory=tuple)
    checks: tuple[CheckRun, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.readiness, Readiness):
            raise ValueError(
                f"readiness must be a Readiness, got {type(self.readiness).__name__}. "
                "A bare string or bool here is how 'could not tell' becomes 'yes'."
            )
        if "#" not in self.pr:
            raise ValueError(
                f"pr must be fully qualified as 'owner/repo#N', got {self.pr!r}. "
                "Two repositories in this fleet had a #521 on the same day; a "
                "bare number identified the wrong pull request."
            )
        if self.readiness is not Readiness.READY and not self.reasons:
            raise ValueError(
                f"readiness={self.readiness.value} with no reasons. A refusal "
                "that does not state what is wrong is unactionable — the "
                "caller cannot fix what it is not told."
            )

    @property
    def exit_code(self) -> int:
        return {
            Readiness.READY: EXIT_READY,
            Readiness.NOT_READY: EXIT_NOT_READY,
            Readiness.CANNOT_DETERMINE: EXIT_UNKNOWN,
        }[self.readiness]

    def render(self) -> str:
        """Human-readable, one line per problem."""
        short = (self.head_sha or "unknown")[:7]
        lines = [f"{self.readiness.value}: {self.pr} @ {short}"]
        lines.extend(f"  - {reason}" for reason in self.reasons)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "readiness": self.readiness.value,
            "pr": self.pr,
            "head_sha": self.head_sha,
            "reasons": list(self.reasons),
            "checks": [
                {
                    "name": c.name,
                    "state": c.state,
                    "head_sha": c.head_sha,
                    "stale": c.stale,
                    "ran": c.ran,
                }
                for c in self.checks
            ],
        }


def _gh_json(args: Sequence[str], timeout: int = 60) -> "tuple[object | None, str | None]":
    """Run a gh command returning JSON. ``(value, error)`` — never raises.

    An unreachable API is a legitimate CANNOT_DETERMINE input, so the
    failure is returned as data rather than thrown; a traceback here would
    be indistinguishable from a real verdict to a shell caller.
    """
    try:
        completed = subprocess.run(
            list(args), capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        return None, "gh is not installed or not on PATH"
    except subprocess.TimeoutExpired:
        return None, f"gh timed out after {timeout}s: {' '.join(args)}"
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        first = detail[0] if detail else f"exit {completed.returncode}"
        return None, f"gh failed: {first}"
    try:
        return json.loads(completed.stdout or "null"), None
    except json.JSONDecodeError as exc:
        return None, f"gh returned unparseable JSON: {exc}"


def readiness(pr: str, repo: str) -> MergeReadiness:
    """Decide whether ``repo#pr`` is mergeable, per check and per commit.

    ``repo`` is required and never guessed. Inferring it from the current
    directory is how a query lands on a same-numbered PR in a sibling
    repository — which happened, and nearly blocked a clean merge on another
    PR's red.
    """
    qualified = f"{repo}#{pr}"

    view, error = _gh_json(
        [
            "gh", "pr", "view", str(pr), "--repo", repo,
            "--json", "headRefOid,mergeable,mergeStateStatus,state",
        ]
    )
    if error is not None or not isinstance(view, dict):
        return MergeReadiness(
            readiness=Readiness.CANNOT_DETERMINE,
            pr=qualified,
            head_sha=None,
            reasons=(
                f"cannot read the pull request: {error or 'unexpected response'}",
                "check the repo name and that gh is authenticated (gh auth status)",
            ),
        )

    head = view.get("headRefOid")
    if not head:
        return MergeReadiness(
            readiness=Readiness.CANNOT_DETERMINE,
            pr=qualified,
            head_sha=None,
            reasons=("the API did not report a head commit for this pull request",),
        )

    if view.get("state") == "MERGED":
        return MergeReadiness(
            readiness=Readiness.NOT_READY,
            pr=qualified,
            head_sha=head,
            reasons=("already merged",),
        )
    if view.get("state") == "CLOSED":
        return MergeReadiness(
            readiness=Readiness.NOT_READY,
            pr=qualified,
            head_sha=head,
            reasons=("closed without merging",),
        )

    runs, error = _gh_json(
        ["gh", "api", f"repos/{repo}/commits/{head}/check-runs", "--paginate"]
    )
    if error is not None or not isinstance(runs, dict):
        return MergeReadiness(
            readiness=Readiness.CANNOT_DETERMINE,
            pr=qualified,
            head_sha=head,
            reasons=(f"cannot read check runs for {head[:7]}: {error or 'unexpected response'}",),
        )

    checks = _to_checks(runs.get("check_runs") or [], head)
    return _decide(qualified, head, checks, view)


def _to_checks(raw: Sequence[dict], head: str) -> tuple[CheckRun, ...]:
    """Normalise API rows, resolving each run's state and its commit."""
    out: list[CheckRun] = []
    for row in raw:
        status = str(row.get("status") or "").upper()
        conclusion = row.get("conclusion")
        # An unfinished run has no conclusion; reporting it as its STATUS
        # keeps "still running" distinct from any verdict.
        state = str(conclusion or status or "UNKNOWN").upper()
        run_sha = row.get("head_sha")
        out.append(
            CheckRun(
                name=str(row.get("name") or "<unnamed>"),
                state=state,
                head_sha=run_sha,
                stale=bool(run_sha) and run_sha != head,
                ran=True,
            )
        )
    return tuple(out)


def _decide(
    qualified: str, head: str, checks: tuple[CheckRun, ...], view: dict
) -> MergeReadiness:
    """Apply the rules, in order, collecting every reason rather than the first."""
    reasons: list[str] = []

    if not checks:
        return MergeReadiness(
            readiness=Readiness.CANNOT_DETERMINE,
            pr=qualified,
            head_sha=head,
            reasons=(
                f"no check runs exist for {head[:7]}",
                "this is NOT a pass: it means CI has not reported on this commit. "
                "Either the workflows have not started yet, or nothing triggers "
                "them for this branch. A leg that never ran is not a leg that passed.",
            ),
            checks=checks,
        )

    stale = [c for c in checks if c.stale]
    failed = [c for c in checks if not c.stale and c.failed]
    pending = [c for c in checks if not c.stale and c.pending]
    skipped = [c for c in checks if not c.stale and c.skipped]

    reasons.extend(c.describe() for c in stale)
    reasons.extend(c.describe() for c in failed)
    reasons.extend(c.describe() for c in pending)

    merge_state = str(view.get("mergeStateStatus") or "").upper()
    mergeable = str(view.get("mergeable") or "").upper()

    if stale or failed or pending:
        if skipped:
            reasons.extend(
                f"(informational) {c.describe()}" for c in skipped
            )
        return MergeReadiness(
            readiness=Readiness.NOT_READY,
            pr=qualified,
            head_sha=head,
            reasons=tuple(reasons),
            checks=checks,
        )

    if mergeable == "CONFLICTING":
        return MergeReadiness(
            readiness=Readiness.NOT_READY,
            pr=qualified,
            head_sha=head,
            reasons=("the branch has conflicts with its base",),
            checks=checks,
        )

    if mergeable == "UNKNOWN" or merge_state == "UNKNOWN":
        return MergeReadiness(
            readiness=Readiness.CANNOT_DETERMINE,
            pr=qualified,
            head_sha=head,
            reasons=(
                "every check on this head passed, but GitHub reports "
                f"mergeable={mergeable or '?'} / mergeStateStatus="
                f"{merge_state or '?'} — it is still computing the merge, "
                "so readiness cannot be confirmed yet. Re-run in a moment.",
            ),
            checks=checks,
        )

    if merge_state == "BLOCKED":
        return MergeReadiness(
            readiness=Readiness.NOT_READY,
            pr=qualified,
            head_sha=head,
            reasons=(
                "every check that ran on this head passed, but GitHub still "
                "reports mergeStateStatus=BLOCKED — a REQUIRED check has no run "
                "on this commit, or a required review is missing. That is the "
                "'never ran' case: it cannot be seen in the list above, because "
                "an absent run has nothing to list.",
            ),
            checks=checks,
        )

    if merge_state == "BEHIND":
        return MergeReadiness(
            readiness=Readiness.NOT_READY,
            pr=qualified,
            head_sha=head,
            reasons=("the branch is behind its base and must be updated first",),
            checks=checks,
        )

    if skipped:
        reasons.extend(f"(informational) {c.describe()}" for c in skipped)

    return MergeReadiness(
        readiness=Readiness.READY,
        pr=qualified,
        head_sha=head,
        reasons=tuple(reasons),
        checks=checks,
    )


# EOF
