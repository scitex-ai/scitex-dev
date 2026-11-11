#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixtures for the disk-hygiene tests. Real files, no mocks for the tree.

The sweep reasons about a real directory tree (SIF families, a live
symlink, tmp leftovers), so the fixtures build one on disk. Only the
process boundary is faked: ``fuser`` results and the process table come
through the engine's ``run``/``read_procs`` seams, and ``now`` is pinned
so nothing sleeps and nothing depends on the wall clock.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

#: 2001-09-09. Older than any window this sweep will ever carry.
ANCIENT_EPOCH = 1_000_000_000
#: A pinned "now" far enough past fixture mtimes that everything reads as
#: stale unless a test deliberately makes it young.
FUTURE_NOW = float(ANCIENT_EPOCH + 400 * 86_400)


def _set_mtime(path: Path, epoch: float) -> None:
    os.utime(path, (epoch, epoch))


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A fake $HOME with the user-scope config armed."""
    armed = tmp_path / ".scitex" / "dev" / "config.yaml"
    armed.parent.mkdir(parents=True)
    armed.write_text("cleanup:\n  disk:\n    enabled: true\n")
    return tmp_path


@pytest.fixture
def unarmed_home(tmp_path: Path) -> Path:
    """A fake $HOME with no config at all — the steady state."""
    return tmp_path / "bare"


@pytest.fixture
def containers(home: Path) -> Path:
    """A fake containers tree: one family, four dated builds, live newest.

    Layout mirrors the incident: ``sac-base.sif -> sac-base-<new>.sif``
    with older dated builds piled beside it.
    """
    fam = home / "containers" / "sac-base"
    fam.mkdir(parents=True)
    names = [
        "sac-base-2026-1022-230924.sif",
        "sac-base-2026-1023-002022.sif",
        "sac-base-2026-1025-093116.sif",
        "sac-base-2026-1027-045501.sif",
    ]
    for i, name in enumerate(names):
        path = fam / name
        path.write_bytes(b"x" * 1024)
        _set_mtime(path, ANCIENT_EPOCH + i * 86_400)
    newest = fam / names[-1]
    (fam / "sac-base.sif").symlink_to(newest.name)
    (fam / "sac-base.def").write_text("bootstrap")
    return home / "containers"


@pytest.fixture
def tmp_with_leftovers(tmp_path: Path) -> Path:
    """A fake /tmp with one stale and one fresh ``ci-*`` dir."""
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    stale = tmp / "ci-scitex_scholar-40045228307-1-3.13"
    stale.mkdir()
    (stale / "work").mkdir()
    (stale / "work" / "out.log").write_bytes(b"y" * 512)
    _set_mtime(stale, ANCIENT_EPOCH)
    fresh = tmp / "ci-scitex_scholar-40119538064-1-3.11"
    fresh.mkdir()
    (fresh / "work").mkdir()
    _set_mtime(fresh, FUTURE_NOW - 3600)
    (tmp / "not-a-runner").mkdir()
    return tmp


# EOF
