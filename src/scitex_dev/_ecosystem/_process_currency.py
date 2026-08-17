#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_ecosystem/_process_currency.py

"""Does a RUNNING process predate the package it imports?

WHY THIS EXISTS, measured 2026-08-16. An orphaned `notifyd` emitted digests
with stale card states for hours. Five mechanisms were eliminated by
measurement — terminal-status predicate, stale snapshot, two databases,
replayed body, cached list — and the cause was none of them:

    the process printed `[scitex-todo]`, the PRE-RENAME package identity
    it did not know a status the installed build knows
    its venv had been upgraded AFTER it started

It was executing bytes loaded at boot from a package that no longer existed
on disk in that form.

THE GAP THIS CLOSES
-------------------
`drift-report` compares pyproject / pypi / github / img / overlay / ci /
editable. EVERY ONE IS AN ON-DISK ARTIFACT. A process holding old bytes has
no on-disk signature at all — dist-info current, wheel current, venv
current, running code stale. The matrix reports that host fully in sync.

`_install_probe` cannot help either: it asks whether code IMPORTS, which is
a question about disk as seen by a NEW import, not about what an existing
PID already mapped.

So this module asks the one question neither can: is this process OLDER than
the code it claims to run?

WHY IT MUST NOT BE A STARTUP CHECK
-----------------------------------
The fleet already HAS a currency gate — `scitex-cards notifyd --help`
refuses outright when the installed build is behind latest, and it stopped a
peer from installing a supervised unit that would have launched stale code.
It runs ONCE, at startup. A process current at launch that goes stale six
hours later when its venv upgrades is precisely what it cannot see, and that
is the normal lifecycle of every long-lived daemon in a fleet that ships
continuously.

A boot-time assertion is being read as a running-state guarantee. So this
check is designed to be re-evaluated from OUTSIDE the process, repeatedly,
without its cooperation.

WHY THE ANSWER IS THREE-VALUED, AND A SCREEN RATHER THAN A VERDICT
------------------------------------------------------------------
`start_time < package_mtime` proves the process STARTED BEFORE the code
changed. It does NOT prove the process is running the old bytes: an import
may post-date startup, a module may have been reloaded, the mtime may have
moved without the content changing. So the strongest honest claim is
MAY_BE_STALE, and confirming it requires a BEHAVIOUR probe — asking the
running thing to do something only the new build does.

    CURRENT        started after the newest package file; nothing to check
    MAY_BE_STALE   started before it; worth a behaviour probe
    UNKNOWN        /proc unreadable, or the package could not be located

UNKNOWN is deliberately NOT folded into CURRENT. "I could not look" reported
as "it is fine" is the defect this whole module exists to remove — and it is
the same conflation `_install_probe` names in its own docstring.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

__all__ = [
    "Currency",
    "ProcessCurrency",
    "newest_package_mtime",
    "process_start_time",
    "describe_process_currency",
]


class Currency(str, Enum):
    """Whether a running process can still be trusted to hold current code."""

    CURRENT = "current"
    MAY_BE_STALE = "may-be-stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProcessCurrency:
    """One process, one package, and whether the first predates the second.

    Every field that could not be read is ``None`` rather than a sentinel
    number, so a caller cannot accidentally compare against a fabricated
    zero and conclude the process is ancient.
    """

    pid: int
    started_at: float | None
    package_mtime: float | None
    verdict: Currency
    reason: str

    def line(self) -> str:
        if self.verdict is Currency.UNKNOWN:
            return f"  pid {self.pid}: UNKNOWN — {self.reason}"
        if self.verdict is Currency.MAY_BE_STALE:
            age = (self.package_mtime or 0) - (self.started_at or 0)
            return (
                f"  pid {self.pid}: MAY BE STALE — started {age / 3600:.1f}h "
                f"before the newest package file. Confirm with a behaviour "
                f"probe; a version string cannot answer this."
            )
        return f"  pid {self.pid}: current"


def process_start_time(pid: int, *, proc: Path = Path("/proc")) -> float | None:
    """Wall-clock start time of ``pid``, or None if it cannot be read.

    Reads field 22 of ``/proc/<pid>/stat`` (start time in clock ticks since
    boot) and anchors it with ``/proc/uptime``. The comm field can contain
    spaces and parentheses, so the split is anchored on the LAST ``)`` —
    splitting on whitespace alone misparses any process whose name contains
    one, which is not exotic (``(sd-pam)``).
    """
    try:
        raw = (proc / str(pid) / "stat").read_text()
        uptime = float((proc / "uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    try:
        after_comm = raw.rsplit(")", 1)[1].split()
        ticks = int(after_comm[19])
    except (IndexError, ValueError):
        return None
    hz = os.sysconf("SC_CLK_TCK")
    if not hz:
        return None
    return (time.time() - uptime) + ticks / hz


def newest_package_mtime(package_root: Path) -> float | None:
    """Newest mtime among the package's ``.py`` files, or None if unreadable.

    The NEWEST rather than the directory's own mtime: a directory mtime moves
    when a file is added or removed and stays put when one is edited in
    place, which is the common case for an upgrade that rewrites files.
    """
    try:
        mtimes = [p.stat().st_mtime for p in package_root.rglob("*.py")]
    except OSError:
        return None
    return max(mtimes) if mtimes else None


def describe_process_currency(
    pid: int,
    package_root: Path,
    *,
    proc: Path = Path("/proc"),
) -> ProcessCurrency:
    """Is ``pid`` older than the newest file in ``package_root``?

    A SCREEN, not a verdict — see the module docstring. MAY_BE_STALE means
    "worth a behaviour probe", never "is running old code".
    """
    started = process_start_time(pid, proc=proc)
    pkg_mtime = newest_package_mtime(package_root)

    if started is None:
        return ProcessCurrency(
            pid, None, pkg_mtime, Currency.UNKNOWN,
            f"cannot read {proc}/{pid}/stat — process gone, or not permitted",
        )
    if pkg_mtime is None:
        return ProcessCurrency(
            pid, started, None, Currency.UNKNOWN,
            f"no readable .py files under {package_root}",
        )
    if started < pkg_mtime:
        return ProcessCurrency(
            pid, started, pkg_mtime, Currency.MAY_BE_STALE,
            "process start precedes the newest package file",
        )
    return ProcessCurrency(
        pid, started, pkg_mtime, Currency.CURRENT,
        "process started after the newest package file",
    )


# EOF
