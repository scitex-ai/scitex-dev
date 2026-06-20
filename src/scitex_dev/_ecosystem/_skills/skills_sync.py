#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Idempotent skills (re-)install with a change report.

Split out of ``skills.py`` to keep that module under the project's
per-file line budget (mirrors ``skills_drift`` / ``skills_verify`` /
``skills_categories``). ``sync_skills`` is re-exported from ``skills`` for
backward-compatible import paths.

``sync_skills`` runs the exact same install path as ``export_skills`` but
snapshots the destination's ``*.md`` leaves before and after, so callers
learn which files were added, updated, removed, or left unchanged. It is
safe to re-run: a no-op sync over an already-current store reports zero
changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# Subtrees we never treat as skill content (mirrors skills._SKIP_DIRS).
_SKIP_DIRS = {"__pycache__", "GITIGNORED", ".git"}


def _snapshot_md_files(dest: Path) -> dict[str, str]:
    """Map every ``*.md`` under ``dest`` to its content (rel-path keyed).

    Used to diff destination state before/after a re-install. A missing
    ``dest`` yields an empty snapshot (first sync). ``read_text`` follows
    symlinks, so a ``--link`` package directory still reports its leaf
    contents.
    """
    snapshot: dict[str, str] = {}
    if not dest.exists():
        return snapshot
    for md_file in sorted(dest.rglob("*.md")):
        if any(
            part in _SKIP_DIRS or part.startswith(".")
            for part in md_file.relative_to(dest).parts[:-1]
        ):
            continue
        try:
            snapshot[str(md_file.relative_to(dest))] = md_file.read_text(
                encoding="utf-8"
            )
        except Exception:
            # Unreadable leaf (e.g. broken symlink) — treat as absent so a
            # later successful read registers as added/updated, never crash.
            continue
    return snapshot


def sync_skills(
    dest: Path,
    *,
    package: Optional[str] = None,
    clean: bool = False,
    source: str = "installed",
    link: bool = False,
    _discover_fn=None,
    _root_fn=None,
    _version_fn=None,
) -> dict[str, object]:
    """Idempotently (re-)install skills into ``dest`` and report what changed.

    Wraps :func:`scitex_dev._ecosystem._skills.skills.export_skills` (the
    exact install path) but snapshots the destination's ``*.md`` leaves
    before and after, so callers learn which files were *added*, *updated*,
    *removed*, or left *unchanged*. Safe to re-run: a no-op sync over an
    already-current store reports zero changes.

    Args:
        dest: Target directory (same semantics as ``export_skills``).
        package: Sync only this package. None syncs all discovered packages.
        clean: Delete each package subdir before re-installing (removed
               leaves then surface in the ``removed`` report).
        source: ``"installed"`` or ``"pypi"`` (passthrough).
        link: Symlink mode (passthrough; only valid with installed source).

    Returns:
        Dict with keys:
          - ``exported``: ``{pkg: [Path, ...]}`` (same as ``export_skills``).
          - ``added``:    sorted rel-paths newly written.
          - ``updated``:  sorted rel-paths whose content changed.
          - ``unchanged``: sorted rel-paths re-written with identical content.
          - ``removed``:  sorted rel-paths present before but gone after.
          - ``changed``:  bool — True iff added/updated/removed is non-empty.
    """
    # Lazy import avoids the circular import (skills.py imports this module
    # at its tail for the re-export).
    from .skills import export_skills

    before = _snapshot_md_files(dest)

    exported = export_skills(
        dest,
        package=package,
        clean=clean,
        source=source,
        link=link,
        _discover_fn=_discover_fn,
        _root_fn=_root_fn,
        _version_fn=_version_fn,
    )

    after = _snapshot_md_files(dest)

    after_keys = set(after)
    before_keys = set(before)
    common = after_keys & before_keys
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    updated = sorted(rel for rel in common if after[rel] != before[rel])
    unchanged = sorted(rel for rel in common if after[rel] == before[rel])

    return {
        "exported": exported,
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "removed": removed,
        "changed": bool(added or updated or removed),
    }


# EOF
