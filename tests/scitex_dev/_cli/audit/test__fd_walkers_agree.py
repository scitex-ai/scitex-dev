#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The two file walkers must return the SAME SET, not similar ones.

`fd_find_files` shells `fd` when it is present and falls back to a stdlib
walk when it is not. `fd` ships on developer machines and NOT on GitHub
runners, so those two paths are exactly split along the local/CI boundary —
which means any disagreement between them is a disagreement about what the
audit grades, and it shows up as "works locally, fails in CI" with no line
of output explaining why.

Measured 2026-08-15 on this repository, before the fallback learned to
filter:

    repo root:  fd=1142   rglob=1227   -> 85 files only CI ever saw
    tests/   :  fd=498    rglob=498    -> no difference

The 85 were `.old/` archives and vendored doc examples — files not in the
repository, graded in CI, invisible locally. scitex-agent-container measured
the downstream effect on their own tree independently: 19-23 lines inspected
in CI against 15 locally, on the SAME COMMIT, in every pair they checked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scitex_dev._cli.audit._fd import (
    _rglob_find_files,
    fd_available,
    fd_find_files,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A git repo with one tracked file, one gitignored, one hidden."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "build").mkdir()
    (repo / ".old").mkdir()
    (repo / "src" / "kept.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "build" / "generated.py").write_text("x = 2\n", encoding="utf-8")
    (repo / ".old" / "archived.py").write_text("x = 3\n", encoding="utf-8")
    (repo / ".gitignore").write_text("build/\n", encoding="utf-8")
    _git(repo, "init", "-q")
    return repo


def test_the_fallback_skips_gitignored_files(tree: Path) -> None:
    """THE DEFECT. `build/generated.py` is not in the repository."""
    # Arrange
    names = None
    # Act
    names = {p.name for p in _rglob_find_files(tree, glob="*.py")}
    # Assert
    assert "generated.py" not in names


def test_the_fallback_skips_hidden_directories(tree: Path) -> None:
    """`fd` runs without --hidden, so it never descends into `.old/`.

    This is the half that would have re-flagged an archived test file in CI
    while the same audit passed locally.
    """
    # Arrange
    names = None
    # Act
    names = {p.name for p in _rglob_find_files(tree, glob="*.py")}
    # Assert
    assert "archived.py" not in names


def test_the_fallback_still_returns_the_real_files(tree: Path) -> None:
    """POSITIVE CONTROL. A walker that filtered everything would pass both
    tests above and audit nothing at all — which is the failure this whole
    thread is about, arrived at from the other side."""
    # Arrange
    names = None
    # Act
    names = {p.name for p in _rglob_find_files(tree, glob="*.py")}
    # Assert
    assert names == {"kept.py"}


@pytest.mark.skipif(fd_available() is None, reason="fd not installed")
def test_both_walkers_return_the_same_set(tree: Path) -> None:
    """THE CONTRACT: equality with `fd`, not approximation of it.

    Skipped where `fd` is absent — which is the CI runner, and is not a
    gap: the synthetic tests above pin the fallback's behaviour directly
    and run everywhere. This one exists so a developer machine proves the
    two paths agree on a real tree rather than on my model of one.
    """
    # Arrange
    expected = set(fd_find_files(tree, glob="*.py"))
    # Act
    actual = set(_rglob_find_files(tree, glob="*.py"))
    # Assert
    assert actual == expected


@pytest.mark.skipif(fd_available() is None, reason="fd not installed")
def test_both_walkers_agree_on_this_repository(tree: Path) -> None:
    """The regression that started this: a REAL tree with .old/ and docs/.

    The synthetic fixture cannot reproduce 85 files of divergence; this
    repository did, and it is the only tree guaranteed present.
    """
    # Arrange
    repo = Path(__file__).resolve().parents[4]
    # Act
    fd_set = set(fd_find_files(repo, glob="*.py"))
    rglob_set = set(_rglob_find_files(repo, glob="*.py"))
    # Assert
    assert rglob_set == fd_set


def test_a_missing_root_is_empty_not_an_error(tmp_path: Path) -> None:
    """Unchanged behaviour, pinned so the new filtering did not break it."""
    # Arrange
    absent = tmp_path / "nope"
    # Act
    found = _rglob_find_files(absent, glob="*.py")
    # Assert
    assert found == []


def test_a_tree_outside_git_still_returns_files(tmp_path: Path) -> None:
    """No git means nothing can be SHOWN to be ignored, so nothing is
    dropped for that reason. Returning empty would be the worse failure:
    an audit that silently grades nothing (see #620)."""
    # Arrange
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "mod.py").write_text("x = 1\n", encoding="utf-8")
    # Act
    found = _rglob_find_files(plain, glob="*.py")
    # Assert
    assert [p.name for p in found] == ["mod.py"]


# EOF
