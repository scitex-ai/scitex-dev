#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply the host-placement declaration during ``ecosystem up``.

Split out of ``_up.py`` (which was already over the line cap) because
"which of these jobs belong on THIS host" is a distinct responsibility
from "reconcile the crontab and the supervisor".

The resolution logic itself is pure and lives in
:mod:`scitex_dev.jobs._placement`; this module is the thin adapter that
runs it during a reconcile and decides what a reconcile should DO with
each answer.

WHY A RECONCILE AND A CHECKER ANSWER DIFFERENTLY
------------------------------------------------
An UNRESOLVABLE placement — a group named while this host declares no
groups — is a hard failure for ``placement check`` and merely a loud
report here, where the job is ARMED anyway.

That asymmetry is deliberate. A reconcile that disarmed a job because it
could not EVALUATE a restriction would read an unknown as a prohibition,
and the blast radius of that reading is a host quietly losing work it
was already doing. A checker has no such blast radius: it reports and
exits non-zero, and nothing stops running because it did.
"""

from __future__ import annotations

import socket
from typing import Callable, Sequence

from ....jobs import JobSpec


def apply_placement(
    jobs: list[JobSpec],
    *,
    host: str | None = None,
    log: Callable[[str], None],
    discover_fn: Callable[[], list] | None = None,
    host_groups: Sequence[str] = (),
) -> tuple[list[JobSpec], list[tuple[str, str]]]:
    """Split ``jobs`` into (armed here, excluded here). Reports as it goes.

    Returns the jobs to act on, plus ``(name, reason)`` for each one left
    out — so the caller can SAY which jobs it skipped and why. A job
    silently missing from a host is precisely the condition this
    mechanism exists to make legible; dropping one quietly would
    reproduce the bug in the fix.

    ``discover_fn`` is the test seam, mirroring ``discover``/``runner``
    elsewhere in the up flow.
    """
    from ....jobs._placement import (
        PlacementUnresolvable,
        decide,
        discover_placement,
    )

    resolved_host = host or socket.gethostname().split(".")[0]
    discover_records = discover_fn or discover_placement

    try:
        records = discover_records()
    except Exception as exc:  # noqa: BLE001 — never wedge the reconcile
        log(
            f"placement: ERROR discovering placement ({exc}); "
            f"arming every discovered job"
        )
        return jobs, []

    if not records:
        # Distinct from "declared, but not for me", and reported as
        # such: this one means the declaration has not been WRITTEN yet,
        # and the fix is to write it. Reading it as "run nothing here"
        # would disarm every host in the fleet the day this ships.
        log(
            "placement: nothing declared anywhere; arming every discovered "
            "job (UNSTATED is 'no opinion yet', not 'run nothing here')"
        )
        return jobs, []

    armed: list[JobSpec] = []
    excluded: list[tuple[str, str]] = []
    for job in jobs:
        try:
            decision = decide(
                job.name,
                records,
                host=resolved_host,
                host_groups=tuple(host_groups),
            )
        except PlacementUnresolvable as exc:
            log(f"placement: UNRESOLVABLE, arming anyway — {exc}")
            armed.append(job)
            continue
        if decision.armed:
            armed.append(job)
        else:
            excluded.append((job.name, decision.reason))

    if excluded:
        log(
            f"placement: {len(excluded)} job(s) not placed on "
            f"{resolved_host}, so not armed here:"
        )
        for name, reason in excluded:
            log(f"  - {name}: {reason}")

    return armed, excluded


__all__ = ["apply_placement"]

# EOF
