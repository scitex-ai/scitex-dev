#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron exec branch-gc`` — the scheduled branch-hygiene pass.

THIS JOB IS INERT UNTIL AN OPERATOR ARMS IT — TWICE.

Being in ``JOB_REGISTRY`` installs nothing (``cron install branch-gc`` is
an explicit act), and even installed, every repo it visits stays DEFAULT
OFF until ``cleanup.branches.enabled: true`` appears in BOTH that repo's
``.scitex/dev/config.yaml`` and the user-scope one. So the steady state of
this job on a fresh machine is: it runs, it reads, it reports, and it
deletes nothing anywhere.

That is deliberate. A scheduled deleter that works out of the box is a
scheduled deleter that deletes something nobody asked it to, once, at 4am,
and the person who finds out is the person whose branch is gone.

The body is a thin wrapper: it resolves which repos to sweep, calls the
shared engine in :mod:`scitex_dev.hygiene`, prints a per-repo report to
stdout (which ``cron exec`` has already redirected into the rotating log)
and returns an exit code. It owns no predicate of its own.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

__all__ = ["BranchGcRunResult", "run_once"]


@dataclass(frozen=True)
class BranchGcRunResult:
    """What the pass did, for the cron dispatcher's exit-code decision."""

    repos: int = 0
    deleted: int = 0
    candidates: int = 0
    kept: int = 0
    aborted: int = 0
    unreadable: int = 0
    error: str | None = None

    @property
    def failed(self) -> bool:
        """True when the WHOLE pass failed, not when one repo was odd."""
        return self.error is not None


def _managed_repos() -> tuple[list[str], str | None]:
    """Every ecosystem checkout that exists on disk, or a stated failure."""
    try:
        from ..._ecosystem._core import ECOSYSTEM
    except Exception as exc:  # noqa: BLE001 - a broken registry is the error
        return [], f"cannot read ECOSYSTEM registry: {exc}"
    repos: list[str] = []
    for info in ECOSYSTEM.values():
        raw = info.get("local_path", "")
        if not raw:
            continue
        path = Path(raw).expanduser()
        if path.is_dir():
            repos.append(str(path))
    if not repos:
        return [], "no ecosystem checkout found on disk"
    return repos, None


def run_once(*, dry_run: bool = False, out: TextIO | None = None) -> BranchGcRunResult:
    """Sweep every managed checkout once. Returns a structured result.

    ``dry_run=True`` forces report-only even for repos whose config armed
    the sweep, so an operator can run the job by hand and see exactly what
    an armed pass would do before arming it.
    """
    sink = out or sys.stdout
    repos, error = _managed_repos()
    if error is not None:
        print(f"branch-gc: skip — {error}", file=sink)
        return BranchGcRunResult(error=error)

    from ...hygiene import exit_code_for, gc_repos

    outcome = gc_repos(repos, apply=not dry_run)
    for result in outcome.results:
        _report(result, sink)
    print(f"branch-gc: {outcome.summary_line()}", file=sink)
    print(f"branch-gc: exit code would be {exit_code_for(outcome)}", file=sink)
    return BranchGcRunResult(
        repos=len(outcome.results),
        deleted=outcome.deleted_count,
        candidates=outcome.candidate_count,
        kept=outcome.kept_count,
        aborted=len(outcome.aborted),
        unreadable=len(outcome.unreadable),
    )


def _report(result, sink: TextIO) -> None:
    """One repo, one block. An UNREADABLE repo is never printed as clean."""
    if result.unreadable:
        print(f"  UNKNOWN  {result.repo}: {result.error}", file=sink)
        return
    if not result.enabled:
        # The expected steady state. Say so in one line with the reason, so
        # a log full of these is legible rather than mysterious.
        print(
            f"  off      {result.repo}: {result.count_before} branch(es); "
            f"{result.config_error or 'cleanup.branches.enabled not set'}",
            file=sink,
        )
        return
    if result.abort_reason:
        print(f"  ABORTED  {result.repo}: {result.abort_reason}", file=sink)
        return
    breakdown = ", ".join(
        f"{key}={value}" for key, value in result.keep_reason_breakdown.items()
    )
    print(
        f"  swept    {result.repo}: {len(result.deleted)} deleted, "
        f"{len(result.kept)} kept ({breakdown or 'none'})",
        file=sink,
    )
    for verdict in result.deleted:
        print(f"      - {verdict.name} ({verdict.landed_source})", file=sink)
    if result.bundle_path:
        print(f"      backup  {result.bundle_path}", file=sink)
        print(f"      restore {result.restore_command}", file=sink)
    if result.exceeds_cap:
        print(
            f"      DEGRADED {result.count_after} branches over cap {result.cap}",
            file=sink,
        )


# EOF
