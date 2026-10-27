#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron exec disk-guard`` — the scheduled disk-hygiene pass.

THIS JOB IS INERT UNTIL AN OPERATOR ARMS IT — TWICE.

Being in ``JOB_REGISTRY`` installs nothing (``cron install disk-guard``
is an explicit act), and even installed, the host stays DEFAULT OFF
until ``cleanup.disk.enabled: true`` appears in
``$HOME/.scitex/dev/config.yaml``. So the steady state of this job on a
fresh machine is: it runs, it measures, it reports, and it deletes
nothing anywhere.

That is deliberate. A scheduled deleter that works out of the box is a
scheduled deleter that deletes something nobody asked it to, once, at
4am, and the person who finds out is the person whose agent won't
restart.

The body is a thin wrapper: it calls the shared engine in
:mod:`scitex_dev.hygiene`, prints a report to stdout (which ``cron
exec`` has already redirected into the rotating log) and returns an
exit code. It owns no predicate of its own.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TextIO

from ..._core.streams import write_stream

__all__ = ["DiskGuardRunResult", "run_once"]


@dataclass(frozen=True)
class DiskGuardRunResult:
    """What the pass did, for the cron dispatcher's exit-code decision."""

    deleted: int = 0
    candidates: int = 0
    kept: int = 0
    freed_bytes: int = 0
    use_before_pct: float | None = None
    use_after_pct: float | None = None
    error: str | None = None

    @property
    def failed(self) -> bool:
        """True when the WHOLE pass failed, not when one candidate was odd."""
        return self.error is not None


def run_once(*, dry_run: bool = False, out: TextIO | None = None) -> DiskGuardRunResult:
    """Sweep this host once. Returns a structured result.

    ``dry_run=True`` forces report-only even when the config armed the
    sweep, so an operator can run the job by hand and see exactly what
    an armed pass would do before arming it.
    """
    sink = out or sys.stdout

    from ...hygiene import sweep_host

    try:
        result = sweep_host(apply=not dry_run)
    except Exception as exc:  # noqa: BLE001 - the pass itself must not crash cron
        write_stream(f"disk-guard: FAILED ({exc})", sink)
        return DiskGuardRunResult(error=str(exc))

    if result.aborted:
        write_stream(f"disk-guard: ABORTED ({result.aborted})", sink)
        return DiskGuardRunResult(error=result.aborted)
    if not result.enabled:
        write_stream(
            f"disk-guard: off — {result.config_error or 'cleanup.disk.enabled not set'}",
            sink,
        )
        return DiskGuardRunResult()
    breakdown = ", ".join(
        f"{key}={value}" for key, value in result.keep_reason_breakdown.items()
    )
    write_stream(
        f"disk-guard: {len(result.deleted)} deleted "
        f"({result.freed_bytes} B freed), {len(result.kept)} kept "
        f"({breakdown or 'none'}); "
        f"use {result.use_before_pct}% -> {result.use_after_pct}%",
        sink,
    )
    for verdict in result.deleted:
        write_stream(f"    - {verdict.path} [{verdict.reason}]", sink)
    return DiskGuardRunResult(
        deleted=len(result.deleted),
        candidates=len(result.candidates),
        kept=len(result.kept),
        freed_bytes=result.freed_bytes,
        use_before_pct=result.use_before_pct,
        use_after_pct=result.use_after_pct,
    )


# EOF
