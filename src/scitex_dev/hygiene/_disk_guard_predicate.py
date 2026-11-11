#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safety legs for disk-guard candidates. Unevaluable reads as KEEP.

Four legs, AND-combined per candidate kind. The legs are ordered
cheapest-first (pattern, age, liveness) so a pass over a host with
nothing to do costs a directory listing and nothing else.

Leg vocabulary (``reason`` strings are stable API — tests and logs key
on them):

- ``protected`` — matches a user ``protect`` glob. Never touched.
- ``live-symlink-target`` — a SIF a live ``<family>.sif`` link resolves
  to. The link is the fleet's pointer to the running base; the file it
  points at is definitionally in use.
- ``within-keep-newest`` — a SIF among the newest N dated builds of its
  family. Rotation keeps history, not just the present.
- ``held-open`` — ``fuser`` (or the fallback scan) shows a live process
  holding the file. Observed 2026-10-27: 22 Apptainer runtimes pinned
  to a superseded base SIF.
- ``too-young`` — mtime newer than the age floor.
- ``fuser-unavailable`` — the open check itself could not run. The leg
  is unevaluable, so it reads as KEEP: deleting without the liveness
  check is exactly the failure mode the check exists for.
- ``build-in-flight`` — a docker build/bake process is running. The
  whole build-cache leg stands down, not just one candidate.
- ``below-threshold`` — use% under the configured threshold. Cache is
  useful; pruning it on a healthy host is churn.
- ``docker-unavailable`` — no docker binary, so no cache to measure or
  prune. KEEP (there is nothing to do, not a failure).
"""

from __future__ import annotations

import fnmatch
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

__all__ = [
    "BuildState",
    "SifFamily",
    "fuser_holds",
    "is_build_in_flight",
    "scan_sif_family",
    "should_prune_build_cache",
]

#: Dated SIF names look like ``sac-base-2026-1027-045501.sif`` — family,
#: a YYYY stamp, then anything. Undated files never match and are never
#: candidates: the sweep rotates dated builds, nothing else.
DATED_SIF_GLOB = "-[12][0-9][0-9][0-9]-*.sif"


@dataclass(frozen=True)
class SifFamily:
    """One rotatable family: dir + live-link name + dated members."""

    name: str
    directory: Path
    live_target: Path | None
    members: tuple[Path, ...]  # oldest first


@dataclass(frozen=True)
class BuildState:
    """What the build-cache leg needs to decide."""

    use_pct: float | None
    docker_present: bool
    build_in_flight: bool


def scan_sif_family(directory: Path, family: str) -> SifFamily:
    """List one family's dated builds, oldest first, resolving the live link."""
    live_link = directory / f"{family}.sif"
    live_target: Path | None = None
    try:
        if live_link.is_symlink():
            live_target = live_link.resolve()
    except OSError:
        live_target = None
    members: list[Path] = []
    try:
        entries = sorted(
            directory.glob(f"{family}{DATED_SIF_GLOB}"),
            key=lambda p: p.stat().st_mtime,
        )
    except OSError:
        entries = []
    for entry in entries:
        try:
            if entry.is_file() and not entry.is_symlink():
                members.append(entry)
        except OSError:
            continue
    return SifFamily(
        name=family,
        directory=directory,
        live_target=live_target,
        members=tuple(members),
    )


def fuser_holds(
    path: Path,
    run: Callable[..., subprocess.CompletedProcess] | None = None,
) -> bool | None:
    """True if a live process holds ``path``. None if unevaluable.

    ``fuser`` exits 0 when something holds the file, 1 when nothing
    does, and anything else (or a missing binary) means the leg cannot
    be evaluated — which the caller reads as KEEP, never as pass.
    """
    runner = run or subprocess.run
    try:
        proc = runner(
            ["fuser", str(path)],
            capture_output=True,
            timeout=15,
        )
    except FileNotFoundError:
        return None
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


def is_build_in_flight(
    read_procs: Callable[[], list[str]] | None = None,
) -> bool | None:
    """True while a docker build/bake runs. None if unevaluable.

    The self-match-safe character classes (``[d]ocker``) keep the
    inspector's own pipeline out of its own results.
    """
    try:
        lines = read_procs() if read_procs is not None else _process_command_lines()
    except Exception:  # noqa: BLE001 - any probe failure is unevaluable
        return None
    import re

    pattern = re.compile(r"[d]ocker\s+(build|buildx)|[b]uildx\s+bake|[b]uildkitd")
    return any(pattern.search(line) for line in lines)


def _process_command_lines() -> list[str]:
    proc = subprocess.run(
        ["ps", "-eo", "args"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if proc.returncode != 0:
        raise OSError(f"ps exited {proc.returncode}")
    return proc.stdout.splitlines()


def should_prune_build_cache(
    state: BuildState,
    threshold_pct: int,
) -> tuple[bool, str]:
    """The build-cache leg as one decision: (prune?, reason)."""
    if not state.docker_present:
        return False, "docker-unavailable"
    if state.build_in_flight:
        return False, "build-in-flight"
    if state.use_pct is None:
        return False, "fuser-unavailable"
    if state.use_pct < threshold_pct:
        return False, "below-threshold"
    return True, "at-threshold"


def matches_protect(path: str, protect: tuple[str, ...]) -> bool:
    """User ``protect`` globs, matched against the full path and basename."""
    base = path.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(base, pattern)
        for pattern in protect
    )


def older_than(
    path: Path, min_age_days: float, now: float | None = None
) -> bool | None:
    """True if mtime is past the floor. None if the mtime is unreadable."""
    try:
        age_days = (
            (now if now is not None else time.time()) - path.stat().st_mtime
        ) / 86_400
    except OSError:
        return None
    return age_days >= min_age_days


def docker_present() -> bool:
    """Whether a docker binary resolves on PATH."""
    return shutil.which("docker") is not None


# EOF
