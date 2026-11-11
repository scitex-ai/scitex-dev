#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The disk-guard engine. Reports by default; deletes only when armed.

FOUR GATES STAND BETWEEN THIS MODULE AND A DELETION
----------------------------------------------------
1. ``DiskCleanupConfig.enabled`` defaults ``False`` at the dataclass
   level, and the loader fails closed.
2. The user-scope config must set ``cleanup.disk.enabled`` to literal
   YAML ``true`` — identity, so typos read as OFF.
3. ``apply`` defaults ``False`` here, independent of config: config-on
   still only reports until an explicit opt-in.
4. The cron job is inert until an operator runs ``cron install`` AND
   arms the config — installing the job alone deletes nothing.

WHAT IT DELETES
---------------
Dated SIF builds superseded by newer ones (never the live symlink
target, never the newest N per family, never anything held open),
stale ``/tmp/ci-*`` runner dirs (age floor + open check), and Docker
build cache (only at/above the use threshold, never mid-build).
Nothing else. No worktree, no checkout, no image, no container, no
volume is ever touched.

Every leg that cannot be evaluated reads as KEEP — see
:mod:`._disk_guard_predicate` for the vocabulary.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Callable

from ._disk_guard_config import load_disk_cleanup_config
from ._disk_guard_model import (
    DiskCandidateKind,
    DiskVerdict,
    HostSweepResult,
)
from ._disk_guard_predicate import (
    BuildState,
    docker_present,
    fuser_holds,
    is_build_in_flight,
    matches_protect,
    older_than,
    scan_sif_family,
    should_prune_build_cache,
)

__all__ = ["sweep_host"]

#: Where the agent-container SIF families live, relative to $HOME.
CONTAINERS_REL = (
    Path(".dotfiles") / "src" / ".scitex" / "agent-container" / "containers"
)


def _use_pct_of(path: str) -> float | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    if usage.total <= 0:
        return None
    return round(100.0 * usage.used / usage.total, 1)


def sweep_host(
    *,
    home: Path | None = None,
    containers_dir: Path | None = None,
    tmp_dir: Path | None = None,
    apply: bool = False,
    max_delete: int | None = None,
    now: float | None = None,
    run: Callable[..., subprocess.CompletedProcess] | None = None,
    read_procs: Callable[[], list[str]] | None = None,
) -> HostSweepResult:
    """One pass over one host. Pure except for the documented seams."""
    host = socket.gethostname()
    config = load_disk_cleanup_config(home)
    result = HostSweepResult(host=host, threshold_pct=config.threshold_pct)
    if not config.enabled:
        result.enabled = False
        result.config_error = config.error or "cleanup.disk.enabled not set"
        return result
    result.enabled = True

    use_before = _use_pct_of("/")
    if use_before is None:
        result.aborted = "could not measure filesystem use"
        return result
    result.use_before_pct = use_before

    base_home = Path(home).expanduser() if home is not None else Path.home()
    containers = (
        Path(containers_dir)
        if containers_dir is not None
        else base_home / CONTAINERS_REL
    )
    tmp = Path(tmp_dir) if tmp_dir is not None else Path("/tmp")

    verdicts: list[DiskVerdict] = []
    verdicts.extend(
        _sif_verdicts(
            containers,
            keep_newest=config.sif_keep_newest,
            protect=config.protect,
            run=run,
        )
    )
    verdicts.extend(
        _tmp_verdicts(
            tmp,
            min_age_days=config.min_age_days,
            protect=config.protect,
            now=now,
            run=run,
        )
    )
    cache_verdict = _cache_verdict(
        use_before,
        threshold_pct=config.threshold_pct,
        read_procs=read_procs,
    )
    if cache_verdict is not None:
        verdicts.append(cache_verdict)

    if max_delete is not None:
        deletable = [v for v in verdicts if v.action == "delete"]
        for extra in deletable[max_delete:]:
            verdicts[verdicts.index(extra)] = DiskVerdict(
                path=extra.path,
                kind=extra.kind,
                size_bytes=extra.size_bytes,
                action="keep",
                reason="over-cap",
            )

    if apply:
        verdicts = _apply_verdicts(verdicts, run=run)
        result.use_after_pct = _use_pct_of("/")
    else:
        result.use_after_pct = use_before

    result.candidates = tuple(verdicts)
    return result


def _sif_verdicts(
    containers: Path,
    *,
    keep_newest: int,
    protect: tuple[str, ...],
    run: Callable[..., subprocess.CompletedProcess] | None,
) -> list[DiskVerdict]:
    verdicts: list[DiskVerdict] = []
    try:
        families = sorted(p.name for p in containers.iterdir() if p.is_dir())
    except OSError:
        return verdicts
    for family in families:
        directory = containers / family
        if not any(directory.glob(f"{family}-*.sif")):
            continue
        scanned = scan_sif_family(directory, family)
        if not scanned.members:
            continue
        keep: set[Path] = set(scanned.members[-keep_newest:])
        if scanned.live_target is not None:
            keep.add(scanned.live_target)
        for member in scanned.members:
            display = str(member)
            if matches_protect(display, protect):
                verdicts.append(
                    _keep(
                        display, DiskCandidateKind.SIF_SUPERSEDED, member, "protected"
                    )
                )
                continue
            if member in keep:
                reason = (
                    "live-symlink-target"
                    if scanned.live_target is not None and member == scanned.live_target
                    else "within-keep-newest"
                )
                verdicts.append(
                    _keep(display, DiskCandidateKind.SIF_SUPERSEDED, member, reason)
                )
                continue
            holds = fuser_holds(member, run=run)
            if holds is None:
                verdicts.append(
                    _keep(
                        display,
                        DiskCandidateKind.SIF_SUPERSEDED,
                        member,
                        "fuser-unavailable",
                    )
                )
                continue
            if holds:
                verdicts.append(
                    _keep(
                        display, DiskCandidateKind.SIF_SUPERSEDED, member, "held-open"
                    )
                )
                continue
            verdicts.append(
                DiskVerdict(
                    path=display,
                    kind=DiskCandidateKind.SIF_SUPERSEDED,
                    size_bytes=_size_of(member),
                    action="delete",
                    reason="superseded",
                )
            )
    return verdicts


def _tmp_verdicts(
    tmp: Path,
    *,
    min_age_days: float,
    protect: tuple[str, ...],
    now: float | None,
    run: Callable[..., subprocess.CompletedProcess] | None,
) -> list[DiskVerdict]:
    verdicts: list[DiskVerdict] = []
    try:
        resolved_tmp = tmp.resolve()
    except OSError:
        return verdicts
    try:
        entries = sorted(tmp.glob("ci-*"))
    except OSError:
        return verdicts
    for entry in entries:
        display = str(entry)
        try:
            resolved = entry.resolve()
            is_dir = entry.is_dir() and not entry.is_symlink()
        except OSError:
            verdicts.append(
                DiskVerdict(
                    display, DiskCandidateKind.CI_TMPDIR, 0, "keep", "unreadable"
                )
            )
            continue
        if resolved == resolved_tmp or resolved_tmp not in resolved.parents:
            verdicts.append(
                DiskVerdict(
                    display, DiskCandidateKind.CI_TMPDIR, 0, "keep", "outside-tmp"
                )
            )
            continue
        if not is_dir:
            continue
        if matches_protect(display, protect) or matches_protect(str(resolved), protect):
            verdicts.append(
                _keep(display, DiskCandidateKind.CI_TMPDIR, entry, "protected")
            )
            continue
        age = older_than(entry, min_age_days, now=now)
        if age is None:
            verdicts.append(
                _keep(display, DiskCandidateKind.CI_TMPDIR, entry, "unreadable")
            )
            continue
        if not age:
            verdicts.append(
                _keep(display, DiskCandidateKind.CI_TMPDIR, entry, "too-young")
            )
            continue
        holds = fuser_holds(entry, run=run)
        if holds is None:
            verdicts.append(
                _keep(display, DiskCandidateKind.CI_TMPDIR, entry, "fuser-unavailable")
            )
            continue
        if holds:
            verdicts.append(
                _keep(display, DiskCandidateKind.CI_TMPDIR, entry, "held-open")
            )
            continue
        verdicts.append(
            DiskVerdict(
                path=display,
                kind=DiskCandidateKind.CI_TMPDIR,
                size_bytes=_tree_size(entry),
                action="delete",
                reason="stale",
            )
        )
    return verdicts


def _cache_verdict(
    use_before: float,
    *,
    threshold_pct: int,
    read_procs: Callable[[], list[str]] | None,
) -> DiskVerdict | None:
    present = docker_present()
    flight = is_build_in_flight(read_procs=read_procs)
    if flight is None and present:
        return DiskVerdict(
            path="docker build cache",
            kind=DiskCandidateKind.BUILD_CACHE,
            size_bytes=0,
            action="keep",
            reason="fuser-unavailable",
        )
    prune, reason = should_prune_build_cache(
        BuildState(
            use_pct=use_before,
            docker_present=present,
            build_in_flight=bool(flight),
        ),
        threshold_pct,
    )
    if not prune:
        # A quiet host reports nothing: below-threshold cache is not a
        # candidate, it is just cache. Only failures to evaluate report.
        if reason in ("docker-unavailable", "below-threshold", "build-in-flight"):
            return None
        return DiskVerdict(
            path="docker build cache",
            kind=DiskCandidateKind.BUILD_CACHE,
            size_bytes=0,
            action="keep",
            reason=reason,
        )
    return DiskVerdict(
        path="docker build cache",
        kind=DiskCandidateKind.BUILD_CACHE,
        size_bytes=0,
        action="delete",
        reason="at-threshold",
    )


def _apply_verdicts(
    verdicts: list[DiskVerdict],
    *,
    run: Callable[..., subprocess.CompletedProcess] | None,
) -> list[DiskVerdict]:
    applied: list[DiskVerdict] = []
    for verdict in verdicts:
        if verdict.action != "delete":
            applied.append(verdict)
            continue
        try:
            if verdict.kind is DiskCandidateKind.BUILD_CACHE:
                runner = run or subprocess.run
                proc = runner(
                    ["docker", "builder", "prune", "-a", "-f"],
                    capture_output=True,
                    timeout=600,
                )
                if proc.returncode != 0:
                    raise OSError(f"docker builder prune exited {proc.returncode}")
            elif verdict.kind is DiskCandidateKind.CI_TMPDIR:
                shutil.rmtree(verdict.path)
            else:
                target = Path(verdict.path)
                if target.is_symlink() or not target.is_file():
                    raise OSError("refuses: not a regular file at delete time")
                target.unlink()
        except (OSError, subprocess.SubprocessError) as exc:
            applied.append(
                DiskVerdict(
                    path=verdict.path,
                    kind=verdict.kind,
                    size_bytes=verdict.size_bytes,
                    action="keep",
                    reason=f"delete-failed: {exc}",
                )
            )
            continue
        applied.append(
            DiskVerdict(
                path=verdict.path,
                kind=verdict.kind,
                size_bytes=verdict.size_bytes,
                action="delete",
                reason=verdict.reason,
                deleted=True,
            )
        )
    return applied


def _keep(
    display: str, kind: DiskCandidateKind, path: Path, reason: str
) -> DiskVerdict:
    return DiskVerdict(
        path=display,
        kind=kind,
        size_bytes=_tree_size(path)
        if kind is DiskCandidateKind.CI_TMPDIR
        else _size_of(path),
        action="keep",
        reason=reason,
    )


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _tree_size(root: Path) -> int:
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                try:
                    total += (Path(dirpath) / name).stat().st_size
                except OSError:
                    continue
    except OSError:
        pass
    return total


# EOF
