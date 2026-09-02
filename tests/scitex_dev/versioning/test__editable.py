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

from scitex_dev.versioning._editable import (
    editable_ahead_behind,
    editable_behind_upstream,
)


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


# -- the second axis: what the TRACKING REMOTE has that HEAD lacks ----------
# Distance from a tag cannot tell "my branch is out of date" from "the tag
# was cut on another branch" — both read as behind > 0. Only this number
# says whether a pull can do anything, so only this number may raise STALE.


def test_behind_upstream_is_zero_when_level_with_the_remote(gitflow_repo):
    # Arrange — develop holds everything origin/develop holds; the newest
    # tag is on main.
    # Act
    result = editable_behind_upstream(gitflow_repo)
    # Assert
    assert result == 0


def test_tag_distance_still_reports_behind_on_that_same_checkout(gitflow_repo):
    # Arrange — the two axes DISAGREE here, which is the whole point: the
    # tree is behind the tag and current with its remote at the same time.
    # Act
    ahead, behind = editable_ahead_behind(gitflow_repo)
    # Assert
    assert (ahead, behind) == (3, 2)


def test_behind_upstream_counts_commits_only_the_remote_has(gitflow_repo):
    # Arrange — rewind develop two commits, so origin/develop genuinely
    # carries work this tree lacks. This is the case a pull DOES fix, and it
    # is the one that must keep raising the alarm.
    _git(gitflow_repo, "reset", "-q", "--hard", "HEAD~2")
    # Act
    result = editable_behind_upstream(gitflow_repo)
    # Assert
    assert result == 2


def test_no_upstream_is_none(tmp_path):
    # Arrange — a repo with commits but no remote at all: no evidence either
    # way, which must read as UNKNOWN upstream, not as "0 behind".
    repo = _init_repo(tmp_path)
    # Act
    result = editable_behind_upstream(repo)
    # Assert
    assert result is None


# EOF
