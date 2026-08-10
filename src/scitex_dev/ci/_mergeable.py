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
cannot be misread, and :func:`readiness` returns a verdict whose exit code a
script can gate on instead of a human squinting at a summary line.

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

Layout
------
This module is the orchestrator. The pieces live next to it so that a
caller needing only one of them does not import the rest:

    _exit_codes.py   the exit-code vocabulary + its import-time guard
    _check_run.py    one check run and what its state means
    _readiness.py    the verdict dataclass, its validator and renderers
    _gh.py           the only place that shells out
"""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from ._check_run import CheckRun
from ._exit_codes import (
    EXIT_NOT_READY,
    EXIT_READY,
    EXIT_UNKNOWN,
    EXIT_USAGE,
    FRAMEWORK_RESERVED_EXIT_CODES,
    ExitCode,
)
from ._gh import gh_json
from ._readiness import MergeReadiness, Readiness

__all__ = [
    "CheckRun",
    "ExitCode",
    "FRAMEWORK_RESERVED_EXIT_CODES",
    "MergeReadiness",
    "Readiness",
    "EXIT_READY",
    "EXIT_NOT_READY",
    "EXIT_UNKNOWN",
    "EXIT_USAGE",
    "readiness",
]


def readiness(pr: str, repo: str) -> MergeReadiness:
    """Decide whether ``repo#pr`` is mergeable, per check and per commit.

    ``repo`` is required and never guessed. Inferring it from the current
    directory is how a query lands on a same-numbered PR in a sibling
    repository — which happened, and nearly blocked a clean merge on another
    PR's red.
    """
    qualified = f"{repo}#{pr}"

    view, error = gh_json(
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

    runs, error = gh_json(
        ["gh", "api", f"repos/{repo}/commits/{head}/check-runs", "--paginate"]
    )
    if error is not None or not isinstance(runs, dict):
        return MergeReadiness(
            readiness=Readiness.CANNOT_DETERMINE,
            pr=qualified,
            head_sha=head,
            reasons=(
                f"cannot read check runs for {head[:7]}: "
                f"{error or 'unexpected response'}",
            ),
        )

    checks = _to_checks(runs.get("check_runs") or [], head)
    return _decide(qualified, head, checks, view)


def _to_checks(raw: Sequence[dict], head: str) -> tuple[CheckRun, ...]:
    """Normalise API rows, marking superseded attempts of the same check.

    A single head can carry SEVERAL runs of one check name — a manual
    re-run, or two workflow runs triggered for identical code (a push and
    the pull request opened from it both match, which is routine here).

    Only the latest attempt per name decides readiness. Measured 2026-08-09:
    py3.12 died mid-step and a second run of the same commit passed.
    Counting every row let the dead attempt poison the verdict forever — no
    re-run could clear it, which is useless exactly when re-runs matter.

    LATEST MEANS MOST RECENTLY CREATED (check-run id), NOT MOST RECENTLY
    STARTED, and the difference is not academic. In the incident above:

        id=93297989333  FAILURE  started 20:33:21   <- created LATER
        id=93297831878  SUCCESS  started 20:44:06   <- created EARLIER,
                                                       queued, ran later

    The passing run belonged to an earlier-created workflow that sat in the
    queue. Ordering by ``started_at`` picks it and calls the check green;
    GitHub's branch protection picks the other one and reports BLOCKED.

    Ordering by start time was this function's first implementation, and it
    was wrong for the reason that matters: **a verifier must model the gate
    that actually decides the merge, not a more sensible gate of its own
    invention.** Being more permissive than branch protection is how a tool
    tells you to merge something the platform will refuse — or worse, waves
    through a failure the platform was right to hold.

    The superseded attempts are NOT discarded. They are marked and reported,
    so a genuinely intermittent check stays visible instead of being quietly
    laundered into a pass by one lucky retry.
    """
    parsed: list[tuple[tuple, CheckRun]] = []
    for row in raw:
        status = str(row.get("status") or "").upper()
        conclusion = row.get("conclusion")
        # An unfinished run has no conclusion; reporting it as its STATUS
        # keeps "still running" distinct from any verdict.
        state = str(conclusion or status or "UNKNOWN").upper()
        run_sha = row.get("head_sha")
        # Creation order first — check-run ids are monotonic, and that is
        # what branch protection uses. Timestamps only break ties for rows
        # with no usable id; a row we cannot place sorts first so it never
        # displaces one we can.
        try:
            created_rank = int(row.get("id"))
        except (TypeError, ValueError):
            created_rank = -1
        ordering = (
            created_rank,
            str(row.get("started_at") or ""),
            str(row.get("completed_at") or ""),
        )
        parsed.append(
            (
                ordering,
                CheckRun(
                    name=str(row.get("name") or "<unnamed>"),
                    state=state,
                    head_sha=run_sha,
                    stale=bool(run_sha) and run_sha != head,
                    ran=True,
                ),
            )
        )

    latest: dict[str, tuple] = {}
    for ordering, check in parsed:
        current = latest.get(check.name)
        if current is None or ordering > current[0]:
            latest[check.name] = (ordering, check)

    out: list[CheckRun] = []
    for ordering, check in parsed:
        winner = latest[check.name]
        is_winner = winner[0] == ordering and winner[1] is check
        out.append(check if is_winner else replace(check, superseded=True))
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

    # Superseded attempts describe a run that a later run of the same check
    # has replaced. They are reported below, never counted.
    current = [c for c in checks if not c.superseded]
    superseded = [c for c in checks if c.superseded]

    stale = [c for c in current if c.stale]
    failed = [c for c in current if not c.stale and c.failed]
    pending = [c for c in current if not c.stale and c.pending]
    skipped = [c for c in current if not c.stale and c.skipped]

    reasons.extend(c.describe() for c in stale)
    reasons.extend(c.describe() for c in failed)
    reasons.extend(c.describe() for c in pending)

    # Surfaced even on a READY verdict: a check that needed a second attempt
    # is a fact the reader should see, not something a lucky retry launders.
    superseded_notes = [
        f"(informational) {c.describe()}"
        for c in superseded
        if not c.passed
    ]

    merge_state = str(view.get("mergeStateStatus") or "").upper()
    mergeable = str(view.get("mergeable") or "").upper()

    if stale or failed or pending:
        if skipped:
            reasons.extend(f"(informational) {c.describe()}" for c in skipped)
        reasons.extend(superseded_notes)
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
    reasons.extend(superseded_notes)

    return MergeReadiness(
        readiness=Readiness.READY,
        pr=qualified,
        head_sha=head,
        reasons=tuple(reasons),
        checks=checks,
    )


# EOF
