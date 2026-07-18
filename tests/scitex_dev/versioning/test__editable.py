#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The editable CONTENT probe against a REAL git repo (no mocks).

``editable_ahead_behind`` reuses ``check_editable_drift``'s git helpers to
answer the only question that is honest for an editable install: is the
working tree behind its own latest release tag? This is the machinery that
non-negotiable #2 rests on — it never consults the frozen metadata version.

Real git, real commits, real tags. A temp repo is a genuine collaborator, not
a mock.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scitex_dev.versioning._editable import editable_ahead_behind


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("v1")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "c1")
    return repo


def test_ahead_only_when_commits_added_after_tag(tmp_path):
    # Arrange — tag v1.0.0, then add two commits on top.
    repo = _init_repo(tmp_path)
    _git(repo, "tag", "v1.0.0")
    (repo / "f.txt").write_text("v2")
    _git(repo, "commit", "-aqm", "c2")
    (repo / "f.txt").write_text("v3")
    _git(repo, "commit", "-aqm", "c3")
    # Act
    result = editable_ahead_behind(repo)
    # Assert
    assert result == (2, 0)


def test_on_tag_is_zero_zero(tmp_path):
    # Arrange — HEAD is exactly the tagged commit.
    repo = _init_repo(tmp_path)
    _git(repo, "tag", "v1.0.0")
    # Act
    result = editable_ahead_behind(repo)
    # Assert
    assert result == (0, 0)


def test_behind_when_tag_is_ahead_of_head(tmp_path):
    # Arrange — tag a later commit, then move HEAD back before it.
    repo = _init_repo(tmp_path)
    (repo / "f.txt").write_text("v2")
    _git(repo, "commit", "-aqm", "c2")
    _git(repo, "tag", "v2.0.0")
    _git(repo, "checkout", "-q", "HEAD~1")
    # Act
    result = editable_ahead_behind(repo)
    # Assert
    assert result == (0, 1)


def test_no_tag_is_none(tmp_path):
    # Arrange — a repo with commits but no v* tag.
    repo = _init_repo(tmp_path)
    # Act
    result = editable_ahead_behind(repo)
    # Assert
    assert result is None


def test_not_a_repo_is_none(tmp_path):
    # Arrange
    plain = tmp_path / "plain"
    plain.mkdir()
    # Act
    result = editable_ahead_behind(plain)
    # Assert
    assert result is None


# EOF
