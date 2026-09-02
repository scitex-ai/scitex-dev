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
    """Run git, and put git's own stderr in the failure message.

    ``check=True`` alone raises a CalledProcessError whose text is the argv
    and an exit code — which says an operation failed but never why, and a
    CI runner can refuse things a laptop allows. The diagnosis has to
    survive the trip back from the runner, so it is raised here.
    """
    out = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    if out.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({out.returncode}) in {repo}:\n"
            f"{out.stdout}{out.stderr}"
        )
    return out.stdout.strip()


def _commit(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text)
    _git(repo, "add", name)
    _git(repo, "commit", "-qm", text)


def _publish(repo: Path, origin: Path) -> Path:
    """Give ``repo`` a real ``origin`` holding exactly what it holds now.

    Built by BARE-CLONING the finished checkout instead of pushing into an
    empty one. Same end state, and it never runs ``git push`` — which a
    self-hosted CI runner can refuse for reasons that have nothing to do
    with the thing under test (measured on PR #785: every push-based variant
    errored on the runner and passed locally).
    """
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(repo), str(origin)],
        check=True,
        capture_output=True,
    )
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "fetch", "-q", "origin")
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    _git(repo, "branch", f"--set-upstream-to=origin/{branch}", branch)
    return origin


@pytest.fixture
def gitflow_repo(tmp_path) -> Path:
    """A REAL repo in the shape every scitex checkout is in, every day.

    Not a fixture of a hypothetical: this is measured sac on 2026-08-31.

    * ``main`` carries the newest release tag (``v1.1.0``);
    * ``HEAD`` is on ``develop``, which branched BEFORE that tag and has its
      own unreleased commits;
    * ``develop`` is EXACTLY level with ``origin/develop`` — a real remote,
      really fetched from, so ``@{u}`` resolves for real.

    So the checkout is simultaneously behind its latest tag and perfectly
    current. Any check that reads only the first half calls this STALE and
    prescribes a pull that git answers with "Already up to date".
    """
    repo = tmp_path / "checkout"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")

    _commit(repo, "f.txt", "base")
    _git(repo, "tag", "v1.0.0")

    _git(repo, "checkout", "-q", "-b", "develop")
    for n in range(3):
        _commit(repo, "f.txt", f"dev{n}")

    # Released commits land on main and are tagged there. Nobody back-merges
    # them into develop — which is normal, and is why develop measures
    # "behind" a tag it will never contain.
    _git(repo, "checkout", "-q", "main")
    for n in range(2):
        _commit(repo, "g.txt", f"rel{n}")
    _git(repo, "tag", "v1.1.0")

    _git(repo, "checkout", "-q", "develop")
    _publish(repo, tmp_path / "origin.git")
    return repo

# EOF
