#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``discover_stores`` — what stores exist on this host, and what they are.

Discovery answers a question that sounds simple and is not: a ``.db`` file
under ``runtime/`` might be one of ours, might belong to another tool, or
might be unreadable. Those are THREE answers, and a function that returns a
list of paths has silently collapsed them into one.

So discovery is three-valued. Every candidate comes back classified:

* ``RECOGNISED`` — it has this primitive's tables,
* ``FOREIGN`` — a real database, but not one of ours,
* ``UNREADABLE`` — it exists and we could not open it (permissions, a
  half-written file, a directory pretending to be one).

``UNREADABLE`` is the one that matters. Dropping it would report a host as
having fewer stores than it does, and "fewer stores than it does" is
exactly the shape of a backup that quietly skips a file.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence

from ._target import DB_SUFFIX, StoreTarget

__all__ = ["DiscoveredStore", "StoreStatus", "discover_stores"]


class StoreStatus(str, Enum):
    """What a discovered file turned out to be."""

    RECOGNISED = "recognised"
    FOREIGN = "foreign"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class DiscoveredStore:
    """One candidate, classified.

    ``schemas`` lists the store names found inside (a file may host several
    schemas). It is empty for anything but ``RECOGNISED`` — empty because
    there are none to report, which ``detail`` explains.
    """

    target: StoreTarget
    status: StoreStatus
    schemas: tuple[str, ...] = ()
    detail: str = ""

    @property
    def is_ours(self) -> bool:
        """Whether this primitive can open it."""
        return self.status is StoreStatus.RECOGNISED

    def describe(self) -> str:
        """One line for a report."""
        text = f"{self.status.value:11} {self.target.locator}"
        if self.schemas:
            text += f"  schemas={list(self.schemas)}"
        if self.detail:
            text += f"  ({self.detail})"
        return text


def discover_stores(
    packages: "Sequence[str] | None" = None,
    *,
    roots: "Iterable[Path] | None" = None,
) -> list[DiscoveredStore]:
    """Find and classify SQLite stores on this host.

    ``packages`` limits the search to those package short names; ``None``
    scans every package directory present. ``roots`` overrides the search
    roots entirely — used by tests, and by anyone pointing discovery at a
    relocated ``runtime/`` tree.

    Postgres stores are NOT discovered: there is nothing on this host to
    enumerate, and guessing at DSNs would be inventing state rather than
    finding it. Construct those targets explicitly.
    """
    candidates = sorted(_candidate_paths(packages, roots))
    return [_classify(path) for path in candidates]


def _candidate_paths(
    packages: "Sequence[str] | None",
    roots: "Iterable[Path] | None",
) -> set[Path]:
    if roots is not None:
        return {
            path
            for root in roots
            for path in Path(root).rglob(f"*{DB_SUFFIX}")
            if path.is_file()
        }

    try:
        from scitex_config._ecosystem import local_state
    except ImportError:
        return set()

    found: set[Path] = set()
    for pkg in packages or _installed_packages(local_state):
        try:
            base = local_state.runtime_path(pkg)
        except Exception:
            continue
        if base.exists():
            found.update(p for p in base.rglob(f"*{DB_SUFFIX}") if p.is_file())
    return found


def _installed_packages(local_state: object) -> list[str]:
    """Package short names that have a ``.scitex`` directory on this host."""
    try:
        root = local_state.user_root()  # type: ignore[attr-defined]
    except Exception:
        return []
    if not root or not Path(root).exists():
        return []
    return sorted(p.name for p in Path(root).iterdir() if p.is_dir())


def _classify(path: Path) -> DiscoveredStore:
    target = StoreTarget.sqlite(path, pkg=_package_of(path))
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return DiscoveredStore(target, StoreStatus.UNREADABLE, detail=str(exc))

    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        return DiscoveredStore(
            target,
            StoreStatus.UNREADABLE,
            detail=f"not a readable SQLite database: {exc}",
        )
    finally:
        connection.close()

    tables = {name for (name,) in rows}
    schemas = tuple(
        sorted(
            name[: -len("_oplog")]
            for name in tables
            if name.endswith("_oplog")
            and f"{name[: -len('_oplog')]}_rows" in tables
            and f"{name[: -len('_oplog')]}_cursor" in tables
        )
    )
    if schemas:
        return DiscoveredStore(target, StoreStatus.RECOGNISED, schemas=schemas)
    return DiscoveredStore(
        target,
        StoreStatus.FOREIGN,
        detail=(
            f"{len(tables)} table(s), none forming a store "
            "(<name>_rows + <name>_oplog + <name>_cursor)"
        ),
    )


def _package_of(path: Path) -> str:
    """Infer the package short name from the runtime-layout path.

    ``.../.scitex/<pkg>/runtime/<pkg>.db`` -> ``<pkg>``. Falls back to the
    file stem when the path does not follow the convention, rather than
    raising: discovery reporting an oddly-placed store with a best-effort
    package name is more useful than discovery refusing to report it.
    """
    parts = path.parts
    if "runtime" in parts:
        index = parts.index("runtime")
        if index > 0:
            return parts[index - 1]
    return path.stem

# EOF
