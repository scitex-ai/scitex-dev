#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real git repositories for the branch-hygiene tests. No mocks.

Every predicate here is a statement about a real repository and a real
worktree, so the fixtures build both. The three worktree shapes the
sweep must tell apart — clean, dirty-and-recent, dirty-and-abandoned —
each get a tree on disk, because the middle one's failure destroys work
that exists nowhere else and a fake cannot demonstrate that it does not.

Ages are controlled through ``GIT_COMMITTER_DATE`` / ``GIT_AUTHOR_DATE``
and through explicit ``os.utime`` on the worktree files, then read back
through each function's ``now`` seam. Nothing here sleeps and nothing
depends on the wall clock.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

#: 2001-09-09. Older than any window this sweep will ever carry.
ANCIENT_EPOCH = 1_000_000_000

#: A "now" far enough past the fixture commits that everything reads as
#: stale unless a test deliberately makes it young.
FUTURE_NOW = float(ANCIENT_EPOCH + 400 * 86_400)


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


def commit(repo: Path, message: str, *, epoch: int = ANCIENT_EPOCH) -> None:
    stamp = f"{epoch} +0000"
    run_git(repo, "add", "-A")
    run_git(
        repo,
        "commit",
        "-q",
        "-m",
        message,
        env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
    )


def touch_tree(path: Path, epoch: float) -> None:
    """Backdate every file under ``path`` except ``.git``."""
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            os.utime(Path(dirpath) / name, (epoch, epoch))


def build_repo(repo: Path) -> Path:
    """develop + main + a handful of branches with known shapes."""
    repo.mkdir(parents=True, exist_ok=True)
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test")
    run_git(repo, "checkout", "-q", "-b", "develop")
    (repo / "base.txt").write_text("base\n")
    commit(repo, "base")
    run_git(repo, "branch", "main")
    run_git(repo, "branch", "cla")
    run_git(repo, "branch", "cla-signatures")
    run_git(repo, "branch", "claude/sweep-1")

    run_git(repo, "checkout", "-q", "-b", "feat/landed")
    (repo / "landed.txt").write_text("landed\n")
    commit(repo, "landed change", epoch=ANCIENT_EPOCH + 10)
    run_git(repo, "checkout", "-q", "develop")
    run_git(repo, "merge", "-q", "--no-ff", "-m", "merge landed", "feat/landed")

    run_git(repo, "checkout", "-q", "-b", "feat/unlanded")
    (repo / "unlanded.txt").write_text("unlanded\n")
    commit(repo, "unlanded change", epoch=ANCIENT_EPOCH + 20)
    run_git(repo, "checkout", "-q", "develop")
    return repo


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository on develop, with landed and unlanded topic branches."""
    return build_repo(tmp_path / "repo")


@pytest.fixture
def repo_with_clean_worktree(repo: Path) -> tuple[Path, Path]:
    """``(repo, worktree)`` where the worktree has no uncommitted work."""
    worktree = repo.parent / "wt-clean"
    run_git(repo, "worktree", "add", "-q", str(worktree), "feat/unlanded")
    touch_tree(worktree, float(ANCIENT_EPOCH))
    return repo, worktree


@pytest.fixture
def repo_with_dirty_worktree(repo: Path) -> tuple[Path, Path]:
    """``(repo, worktree)`` carrying an uncommitted, freshly-touched file."""
    worktree = repo.parent / "wt-dirty"
    run_git(repo, "worktree", "add", "-q", str(worktree), "feat/unlanded")
    (worktree / "in-progress.txt").write_text("half-finished\n")
    os.utime(worktree / "in-progress.txt", (FUTURE_NOW, FUTURE_NOW))
    return repo, worktree


@pytest.fixture
def repo_with_abandoned_worktree(repo: Path) -> tuple[Path, Path]:
    """``(repo, worktree)`` carrying uncommitted work nobody has touched."""
    worktree = repo.parent / "wt-abandoned"
    run_git(repo, "worktree", "add", "-q", str(worktree), "feat/unlanded")
    (worktree / "abandoned.txt").write_text("forgotten\n")
    touch_tree(worktree, float(ANCIENT_EPOCH))
    return repo, worktree


# EOF
