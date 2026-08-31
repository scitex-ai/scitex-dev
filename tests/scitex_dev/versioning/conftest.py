#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real environment manipulation — no monkeypatch.

``os.environ`` IS the production collaborator here: ``_cache`` and ``_warn``
read it live, on purpose, so a container or a test can redirect them. The
honest way to test that is to set the real variable and put it back
afterwards — which is all this fixture does.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def env():
    """Set/unset real env vars for one test; restore exactly on teardown."""
    saved: dict[str, str | None] = {}

    def _set(name: str, value: str | None) -> None:
        if name not in saved:
            saved[name] = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    yield _set

    for name, old in saved.items():
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


@pytest.fixture
def gitflow_repo(tmp_path) -> Path:
    """A REAL repo in the shape every scitex checkout is in, every day.

    Not a fixture of a hypothetical: this is measured sac on 2026-08-31.

    * ``main`` carries the newest release tag (``v1.1.0``);
    * ``HEAD`` is on ``develop``, which branched BEFORE that tag and has its
      own unreleased commits;
    * ``develop`` is EXACTLY level with ``origin/develop`` — a real bare
      remote, really pushed to, so ``@{u}`` resolves for real.

    So the checkout is simultaneously behind its latest tag and perfectly
    current. Any check that reads only the first half calls this STALE and
    prescribes a pull that git answers with "Already up to date".
    """
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True
    )
    repo = tmp_path / "checkout"
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(repo)],
        check=True,
        capture_output=True,
    )
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")

    (repo / "f.txt").write_text("base")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "tag", "v1.0.0")
    _git(repo, "push", "-q", "origin", "main")

    _git(repo, "checkout", "-q", "-b", "develop")
    for n in range(3):
        (repo / "f.txt").write_text(f"dev{n}")
        _git(repo, "commit", "-aqm", f"dev{n}")
    _git(repo, "push", "-q", "-u", "origin", "develop")

    # Released commits land on main and are tagged there. Nobody back-merges
    # them into develop — which is normal, and is why develop measures
    # "behind" a tag it will never contain.
    _git(repo, "checkout", "-q", "main")
    for n in range(2):
        (repo / "g.txt").write_text(f"rel{n}")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", f"rel{n}")
    _git(repo, "tag", "v1.1.0")
    _git(repo, "push", "-q", "origin", "main", "--tags")

    _git(repo, "checkout", "-q", "develop")
    return repo


# EOF
