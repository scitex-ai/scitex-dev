#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real git repos for the branch-GC tests. No mocks of the thing under test.

Every predicate leg is a statement about a real repository, so the fixture
builds one: a develop base, a fast-forward landing, a MULTI-commit squash
landing (the shape ``git branch --merged`` and ``git cherry`` are both
blind to), a cherry-picked landing, an unlanded branch, a protected
``release/*``, and one branch whose tip commit is ancient while its ref was
created seconds ago — the exact shape of the 2026-08-08 incident.

Ages are controlled through ``GIT_COMMITTER_DATE``/``GIT_AUTHOR_DATE`` and
read back through the engine's ``now`` seam, so no test depends on wall
clock or on sleeping.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

#: Far enough in the future that both age signals of every fixture branch
#: read as OLD. Used by tests that need the age leg to PASS.
FUTURE_OFFSET_DAYS = 400

ANCIENT_EPOCH = 1_000_000_000  # 2001-09-09, comfortably older than any floor


def run_git(repo: Path, *args: str, env: dict | None = None) -> str:
    merged = dict(os.environ)
    merged.update(
        {
            "GIT_CONFIG_GLOBAL": str(repo / ".gitconfig-none"),
            "GIT_CONFIG_SYSTEM": str(repo / ".gitconfig-none"),
        }
    )
    if env:
        merged.update(env)
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=merged,
    )
    return proc.stdout.strip()


def _commit(repo: Path, message: str, *, epoch: int | None = None) -> None:
    env = None
    if epoch is not None:
        stamp = f"{epoch} +0000"
        env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", message, env=env)


def build_repo(repo: Path) -> Path:
    """Build the shared fixture repository and return its path."""
    repo.mkdir(parents=True, exist_ok=True)
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test")
    run_git(repo, "checkout", "-q", "-b", "develop")
    (repo / "base.txt").write_text("base\n")
    _commit(repo, "base", epoch=ANCIENT_EPOCH)
    run_git(repo, "branch", "main")

    # 1. Ancestor landing: --no-ff merge, branch ref kept.
    run_git(repo, "checkout", "-q", "-b", "feature/landed-ff")
    (repo / "ff.txt").write_text("ff\n")
    _commit(repo, "ff change", epoch=ANCIENT_EPOCH + 10)
    run_git(repo, "checkout", "-q", "develop")
    run_git(repo, "merge", "-q", "--no-ff", "-m", "merge ff", "feature/landed-ff")

    # 2. MULTI-commit squash landing. Not an ancestor, and `git cherry`
    #    cannot see it either (the squash patch equals the SUM of the two
    #    commits, not either one). Only a merged-PR lookup knows.
    run_git(repo, "checkout", "-q", "-b", "feature/squashed", "develop")
    (repo / "sq1.txt").write_text("one\n")
    _commit(repo, "squash part one", epoch=ANCIENT_EPOCH + 20)
    (repo / "sq2.txt").write_text("two\n")
    _commit(repo, "squash part two", epoch=ANCIENT_EPOCH + 30)
    run_git(repo, "checkout", "-q", "develop")
    run_git(repo, "merge", "-q", "--squash", "feature/squashed")
    _commit(repo, "squashed feature", epoch=ANCIENT_EPOCH + 40)

    # 3. Cherry-picked landing: patch-equivalent, not an ancestor.
    run_git(repo, "checkout", "-q", "-b", "feature/picked", "main")
    (repo / "pick.txt").write_text("pick\n")
    _commit(repo, "picked change", epoch=ANCIENT_EPOCH + 50)
    picked = run_git(repo, "rev-parse", "HEAD")
    run_git(repo, "checkout", "-q", "develop")
    run_git(repo, "cherry-pick", picked)

    # 4. Never landed.
    run_git(repo, "checkout", "-q", "-b", "feature/unlanded", "develop")
    (repo / "un.txt").write_text("un\n")
    _commit(repo, "unlanded change", epoch=ANCIENT_EPOCH + 60)

    # 5. Protected family, landed and ancient — must survive anyway.
    run_git(repo, "checkout", "-q", "-b", "release/1.0", "develop")

    # 6. The incident shape: an ANCIENT tip commit on a ref created NOW.
    run_git(repo, "checkout", "-q", "-b", "relocation/residency", "feature/landed-ff")

    run_git(repo, "checkout", "-q", "develop")
    return repo


def enable_cleanup(repo: Path, home: Path, **branch_keys) -> None:
    """Arm BOTH config surfaces for ``repo``. Tests that want OFF skip this."""
    body = ["cleanup:", "  branches:", "    enabled: true"]
    for key, value in branch_keys.items():
        body.append(f"    {key.replace('_', '-')}: {value}")
    for root in (repo, home):
        target = root / ".scitex" / "dev" / "config.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(body) + "\n", encoding="utf-8")


def future_now(days: int = FUTURE_OFFSET_DAYS) -> float:
    """A ``now`` far enough ahead that every fixture branch reads as OLD."""
    return time.time() + days * 86_400


def merged_pr_for(*branches: str):
    """A ``PrLookup`` that answers True for ``branches`` and False otherwise."""
    wanted = set(branches)

    def _lookup(_repo, branch):
        return branch in wanted

    return _lookup


def no_open_pr(_repo, _branch):
    return False


def no_active_work():
    return set()


@pytest.fixture(scope="session")
def _repo_template(tmp_path_factory):
    """Build the fixture repo ONCE per session.

    Building it costs ~15 git invocations; copying it costs one directory
    walk. Since several tests DELETE branches, each still gets its own
    private copy — the template is never handed out directly.
    """
    yield build_repo(tmp_path_factory.mktemp("template") / "pkg")


@pytest.fixture
def repo(_repo_template, tmp_path):
    """A private, mutable copy of the fixture repository."""
    target = tmp_path / "pkg"
    shutil.copytree(_repo_template, target)
    yield target


@pytest.fixture
def home(tmp_path):
    """An isolated ``$HOME`` so no test reads the operator's real config."""
    target = tmp_path / "home"
    target.mkdir(parents=True, exist_ok=True)
    yield target


def branches_in(repo: Path) -> list[str]:
    out = run_git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    return [line.strip() for line in out.splitlines() if line.strip()]


# EOF
