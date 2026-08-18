#!/usr/bin/env python3
"""When is a periodic job due, and how are jobs kept off each other's toes.

Pure functions, no clock of their own and no I/O — the caller passes
``now`` and the last-run table, so the whole module is testable without
sleeping. The supervisor's tick calls :func:`due_jobs` and runs what
comes back.

WHY THIS EXISTS. Periodic jobs used to be lowered into ~34 crontab
lines. Operator ruling 2026-08-18: 「crontab ではなく、専門サービスで
お願いします」 — one resident scheduler owns the clock, and cron is not
used at all. A crontab holding one line per job cannot be read, does not
scale, and (measured on this fleet) put **28 jobs on the same second**
at 00:00 because ``*/30``, ``*/10``, ``*/5`` and ``0 * * * *`` all
include minute zero.

THE OFFSET IS ALPHABETICAL, NOT HASHED, and that is a deliberate
trade. A hash spreads jobs perfectly and makes "why did this run now?"
unanswerable during an incident — you cannot recompute it in your head,
so every investigation starts by re-deriving the schedule. Sorted
position is worse at spreading and better at being read: the offset is
`index * spacing`, and the index is alphabetical order among the
packages that declare jobs. Four packages declare them today, so the
spread is ample.
"""

from __future__ import annotations

import logging
from typing import Iterable, Mapping, Sequence

from ..jobs import JobSpec

_logger = logging.getLogger(__name__)

#: Seconds between adjacent packages' offsets. With four packages that
#: puts them at 0/20/40/60s — comfortably apart for jobs whose real work
#: is seconds, and small enough to stay inside a one-minute cadence.
DEFAULT_SPACING_SEC = 20.0

#: systemd-style duration suffixes. Only the ones JobSpec actually uses;
#: an unknown suffix raises rather than being guessed at, because a
#: silently-misparsed cadence is a job running at the wrong rate forever.
_UNITS = {
    "s": 1.0,
    "sec": 1.0,
    "min": 60.0,
    "m": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "d": 86400.0,
}


def parse_duration(text: str) -> float:
    """``"15min"`` -> ``900.0``. Raises on anything it cannot parse.

    Deliberately strict. The alternative — returning a default on an
    unrecognised string — turns a typo into a job that runs at some
    other rate and never complains.
    """
    raw = text.strip().lower()
    if not raw:
        raise ValueError("empty duration")
    digits = ""
    idx = 0
    while idx < len(raw) and (raw[idx].isdigit() or raw[idx] == "."):
        digits += raw[idx]
        idx += 1
    suffix = raw[idx:].strip()
    if not digits:
        raise ValueError(f"duration {text!r} has no leading number")
    unit = _UNITS.get(suffix or "s")
    if unit is None:
        raise ValueError(
            f"duration {text!r}: unknown unit {suffix!r}; "
            f"expected one of {sorted(_UNITS)}"
        )
    return float(digits) * unit


def package_of(job_name: str) -> str:
    """The owning package, read off the job name.

    Names are ``<package>.<verb>-<noun>`` or a legacy bare slug. A bare
    slug has no package prefix, so it answers ``""`` — which groups all
    legacy names together rather than inventing a package for each.
    """
    return job_name.split(".", 1)[0] if "." in job_name else ""


def cadence_sec(job: JobSpec) -> float | None:
    """How often this job wants to run, or ``None`` if it is not periodic.

    ``kind="service"`` is not periodic — it runs continuously — so it
    answers ``None`` and the caller leaves it to the child-restart path.
    """
    if job.kind == "service":
        return None
    if job.on_unit_active_sec:
        return parse_duration(job.on_unit_active_sec)
    if job.schedule:
        return _cadence_from_cron(job.schedule)
    return None


def _cadence_from_cron(expr: str) -> float | None:
    """Approximate a 5-field cron expression as an interval.

    Only the shapes this fleet actually declares are recognised:
    ``*/N`` in a field, and a fixed value. Anything else answers
    ``None`` — UNKNOWN, not a guessed default — so the caller can
    report it rather than run the job at an invented rate.
    """
    parts = expr.split()
    if len(parts) != 5:
        return None
    minute, hour, dom, month, dow = parts
    # A constrained day-of-week or month is NOT an interval. "0 9 * * 1-5"
    # fires on weekdays only; calling it "every 86400s" would schedule it on
    # Saturdays too. Caught by its own test — the first draft read only the
    # minute and hour fields and silently answered daily.
    if dow != "*" or month != "*":
        return None
    if minute.startswith("*/") and hour == "*":
        return float(minute[2:]) * 60.0
    if minute.isdigit() and hour.startswith("*/"):
        return float(hour[2:]) * 3600.0
    if minute.isdigit() and hour == "*":
        return 3600.0
    if minute.isdigit() and hour.isdigit() and dom == "*":
        return 86400.0
    return None


def offsets_for(packages: Iterable[str], *, spacing: float = DEFAULT_SPACING_SEC
                ) -> dict[str, float]:
    """Assign each package a start offset by ALPHABETICAL position.

    Readable on purpose: the offset of a package is its index in sorted
    order times ``spacing``, so anyone can recompute it from the package
    list without running code. See the module docstring for why this
    beats hashing.
    """
    ordered = sorted({p for p in packages})
    return {name: idx * spacing for idx, name in enumerate(ordered)}


def is_due(
    job: JobSpec,
    *,
    now: float,
    last_run: float | None,
    offset: float = 0.0,
) -> bool:
    """Has ``job`` reached its next run time?

    ``last_run=None`` means "never run in this scheduler's memory". Such
    a job is due only once ``now`` has passed its offset, so a cold start
    does not fire every job in the same instant — which is the exact
    pile-up this design exists to remove.
    """
    cadence = cadence_sec(job)
    if cadence is None or cadence <= 0:
        return False
    if last_run is None:
        return now >= offset
    return (now - last_run) >= cadence


def due_jobs(
    jobs: Sequence[JobSpec],
    *,
    now: float,
    last_runs: Mapping[str, float],
    offsets: Mapping[str, float] | None = None,
) -> list[JobSpec]:
    """Every periodic job that should start now, in a stable order.

    Sorted by name so two ticks with identical inputs produce identical
    output — a scheduler whose order wobbles makes its own logs
    unreadable.
    """
    if offsets is None:
        offsets = offsets_for(package_of(j.name) for j in jobs)
    due = [
        job
        for job in jobs
        if is_due(
            job,
            now=now,
            last_run=last_runs.get(job.name),
            offset=offsets.get(package_of(job.name), 0.0),
        )
    ]
    return sorted(due, key=lambda j: j.name)


def unschedulable(jobs: Sequence[JobSpec]) -> list[tuple[str, str]]:
    """Periodic-kind jobs whose cadence could not be determined.

    Returned rather than logged-and-dropped: a job the scheduler cannot
    place is invisible otherwise, and "it never ran" looks identical to
    "it was never scheduled". The caller reports these by name.
    """
    out: list[tuple[str, str]] = []
    for job in jobs:
        if job.kind == "service":
            continue
        try:
            if cadence_sec(job) is None:
                out.append((job.name, job.schedule or "<no cadence declared>"))
        except ValueError as exc:
            out.append((job.name, str(exc)))
    return out
