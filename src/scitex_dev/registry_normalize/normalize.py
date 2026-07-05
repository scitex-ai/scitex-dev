#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Move-planning + execution engine for ``scitex-dev registry-normalize``.

Builds on top of ``scan.py`` (the single source of truth for "what counts
as drift") to produce a plan of ``<from> -> <to>`` moves, then optionally
executes it. Safety rules (non-negotiable, operator-approved):

- Dry-run by default; only ``confirm=True`` touches disk.
- Archive, never delete — every move has a destination.
- Service-safe: a ``*.pid`` file naming a currently-alive process is
  SKIPPED, not moved. A ``*.sock`` file is ALWAYS skipped (liveness is
  not cheaply determinable for sockets) — remove manually if stale.
- Only the drift kinds in ``scan.MOVABLE_KINDS`` are auto-moved.
  Config-naming drift, stray ``__pycache__``, and venv-naming drift are
  reported by the PS-181 audit rule but require manual attention — see
  the module docstring in ``scan.py`` for why.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .scan import MOVABLE_KINDS, DriftItem, scan_pkg_dir

STATUS_PLANNED = "planned"
STATUS_MOVED = "moved"
STATUS_SKIPPED = "skipped"


@dataclass(frozen=True)
class MoveResult:
    """One planned (or executed) move."""

    src: str
    dest: str | None
    status: str  # "planned" | "moved" | "skipped"
    detail: str


def _read_pid(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    first_line = text.splitlines()[0].strip() if text else ""
    try:
        return int(first_line)
    except ValueError:
        return None


def _pid_alive(pid: int) -> bool:
    """True iff *pid* is a currently-running process.

    ``os.kill(pid, 0)`` sends no signal — it only checks existence /
    permission. ``ProcessLookupError`` means the process is gone;
    ``PermissionError`` means it exists but we don't own it (still
    "alive" from our perspective — don't touch it).
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _plan_one(item: DriftItem, pkg_dir: Path) -> MoveResult | None:
    if item.kind not in MOVABLE_KINDS:
        return None
    src = Path(item.path)

    if src.suffix == ".pid":
        pid = _read_pid(src)
        if pid is not None and _pid_alive(pid):
            return MoveResult(
                str(src), None, STATUS_SKIPPED, f"SKIPPED (live pid {pid})"
            )
    if src.suffix == ".sock":
        return MoveResult(
            str(src),
            None,
            STATUS_SKIPPED,
            "SKIPPED (socket, assumed live — remove manually if stale)",
        )

    assert item.dest is not None  # every MOVABLE_KINDS item carries a dest
    dest = pkg_dir / item.dest
    return MoveResult(str(src), str(dest), STATUS_PLANNED, f"{src} -> {dest}")


def build_plan(pkg_dir: Path) -> list[MoveResult]:
    """Return the ordered list of moves ``scan_pkg_dir(pkg_dir)`` implies.

    Pure planning — never touches disk. Skips (pid-alive, socket) are
    included in the returned list with ``status="skipped"`` so callers
    can report them without treating them as an error.
    """
    items = scan_pkg_dir(pkg_dir)
    plan: list[MoveResult] = []
    for item in items:
        result = _plan_one(item, pkg_dir)
        if result is not None:
            plan.append(result)
    return plan


def execute_plan(plan: list[MoveResult]) -> list[MoveResult]:
    """Execute every ``status="planned"`` entry in *plan*, moving files/dirs.

    Entries already ``skipped`` pass through unchanged. Returns a new
    list with executed entries marked ``status="moved"``.

    ``shutil.move`` silently OVERWRITES an existing destination — on a
    repeated run against a package that keeps regenerating the same
    loose file (the realistic recurring-drift case this tool exists
    for), that would clobber the previously-archived/relocated file
    with no copy and no warning: a de facto delete despite the
    archive-not-delete invariant. Check for a destination collision
    immediately before each move and skip it instead, since deciding
    HOW to disambiguate (overwrite vs. rename vs. merge) is a judgment
    call the operator should make, not something to guess silently.
    """
    executed: list[MoveResult] = []
    for entry in plan:
        if entry.status != STATUS_PLANNED:
            executed.append(entry)
            continue
        src = Path(entry.src)
        dest = Path(entry.dest)  # type: ignore[arg-type]
        if dest.exists():
            executed.append(
                MoveResult(
                    entry.src,
                    entry.dest,
                    STATUS_SKIPPED,
                    f"SKIPPED (destination already exists: {dest} — "
                    f"resolve manually to avoid overwriting it)",
                )
            )
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        executed.append(MoveResult(entry.src, entry.dest, STATUS_MOVED, entry.detail))
    return executed


@dataclass
class NormalizeReport:
    """Result of one ``registry-normalize <pkg>`` invocation."""

    pkg: str
    pkg_dir: str
    confirmed: bool
    moves: list[MoveResult]
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "pkg": self.pkg,
            "pkg_dir": self.pkg_dir,
            "confirmed": self.confirmed,
            "error": self.error,
            "moves": [
                {
                    "src": m.src,
                    "dest": m.dest,
                    "status": m.status,
                    "detail": m.detail,
                }
                for m in self.moves
            ],
        }


def run_registry_normalize(
    pkg: str,
    *,
    confirm: bool = False,
    scitex_dir: Path,
) -> NormalizeReport:
    """Plan (and, iff ``confirm=True``, execute) the drift-fix moves for *pkg*.

    *scitex_dir* is the already-resolved ``$SCITEX_DIR`` root (default
    ``~/.scitex``) — callers resolve it once (e.g. via
    ``scitex_config.local_state.user_root()``) so this function stays
    trivially testable against a ``tmp_path`` fixture.
    """
    pkg_dir = scitex_dir / pkg
    if not pkg_dir.is_dir():
        return NormalizeReport(
            pkg=pkg,
            pkg_dir=str(pkg_dir),
            confirmed=confirm,
            moves=[],
            error=f"no such package state dir: {pkg_dir}",
        )

    plan = build_plan(pkg_dir)
    moves = execute_plan(plan) if confirm else plan
    return NormalizeReport(pkg=pkg, pkg_dir=str(pkg_dir), confirmed=confirm, moves=moves)


# EOF
