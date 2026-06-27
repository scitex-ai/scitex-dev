#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for `ecosystem sync` (_sync._sync_one) — real git repos, no mocks.

The safety rails are the whole point, so they're exercised against actual git
repositories built in tmp_path. One assertion per test (STX-TQ007), AAA markers
throughout (STX-TQ002); shared per-scenario setup lives in fixtures.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scitex_dev._cli.ecosystem._cmds._sync import _emit_pulled_events, _sync_one


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.DEVNULL
    ).strip()


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "develop")
    _git(path, "config", "user.email", "t@t.t")
    _git(path, "config", "user.name", "t")


def _commit(repo: Path, fname: str, body: str) -> str:
    (repo / fname).write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", body)
    return _git(repo, "rev-parse", "HEAD")


def _make_origin_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    """A bare 'origin' on develop + a local clone tracking it."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    _init_repo(seed)
    _commit(seed, "f.txt", "c1")
    subprocess.check_call(
        ["git", "clone", "-q", "--bare", str(seed), str(origin)],
        stderr=subprocess.DEVNULL,
    )
    clone = tmp_path / "clone"
    subprocess.check_call(
        ["git", "clone", "-q", str(origin), str(clone)], stderr=subprocess.DEVNULL
    )
    _git(clone, "config", "user.email", "t@t.t")
    _git(clone, "config", "user.name", "t")
    _git(clone, "checkout", "-q", "develop")
    return origin, clone


def _advance_origin(tmp_path: Path, origin: Path, body: str) -> None:
    """Add a commit to origin/develop via a throwaway clone + push."""
    work = tmp_path / f"work-{body}"
    subprocess.check_call(
        ["git", "clone", "-q", str(origin), str(work)], stderr=subprocess.DEVNULL
    )
    _git(work, "config", "user.email", "t@t.t")
    _git(work, "config", "user.name", "t")
    _git(work, "checkout", "-q", "develop")
    _commit(work, "f.txt", body)
    _git(work, "push", "-q", "origin", "develop")


# -- fast-forward pull (origin one ahead, clean clone) --------------------


@pytest.fixture
def ff_pull(tmp_path):
    origin, clone = _make_origin_and_clone(tmp_path)
    before = _git(clone, "rev-parse", "develop")
    _advance_origin(tmp_path, origin, "c2")
    row = _sync_one("pkg", {"local_path": str(clone)}, dry_run=False)
    return {"row": row, "clone": clone, "before": before}


def test_ff_pull_action_is_pulled(ff_pull):
    # Arrange
    row = ff_pull["row"]
    # Act
    action = row["action"]
    # Assert
    assert action == "pulled"


def test_ff_pull_reports_behind_one(ff_pull):
    # Arrange
    row = ff_pull["row"]
    # Act
    behind = row["behind"]
    # Assert
    assert behind == 1


def test_ff_pull_advances_local_develop(ff_pull):
    # Arrange
    clone, before = ff_pull["clone"], ff_pull["before"]
    # Act
    after = _git(clone, "rev-parse", "develop")
    # Assert
    assert after != before


# -- dry-run (reports, never merges) --------------------------------------


@pytest.fixture
def dry_run_pull(tmp_path):
    origin, clone = _make_origin_and_clone(tmp_path)
    before = _git(clone, "rev-parse", "develop")
    _advance_origin(tmp_path, origin, "c2")
    row = _sync_one("pkg", {"local_path": str(clone)}, dry_run=True)
    return {"row": row, "clone": clone, "before": before}


def test_dry_run_action_is_would_pull(dry_run_pull):
    # Arrange
    row = dry_run_pull["row"]
    # Act
    action = row["action"]
    # Assert
    assert action == "would-pull"


def test_dry_run_does_not_move_local_develop(dry_run_pull):
    # Arrange
    clone, before = dry_run_pull["clone"], dry_run_pull["before"]
    # Act
    after = _git(clone, "rev-parse", "develop")
    # Assert
    assert after == before


# -- dirty checkout (skip, never clobber) ---------------------------------


@pytest.fixture
def dirty_checkout(tmp_path):
    origin, clone = _make_origin_and_clone(tmp_path)
    before = _git(clone, "rev-parse", "develop")
    _advance_origin(tmp_path, origin, "c2")
    (clone / "f.txt").write_text("local uncommitted edit")
    row = _sync_one("pkg", {"local_path": str(clone)}, dry_run=False)
    return {"row": row, "clone": clone, "before": before}


def test_dirty_checkout_action_is_dirty(dirty_checkout):
    # Arrange
    row = dirty_checkout["row"]
    # Act
    action = row["action"]
    # Assert
    assert action == "dirty"


def test_dirty_checkout_develop_untouched(dirty_checkout):
    # Arrange
    clone, before = dirty_checkout["clone"], dirty_checkout["before"]
    # Act
    after = _git(clone, "rev-parse", "develop")
    # Assert
    assert after == before


def test_dirty_checkout_preserves_local_edit(dirty_checkout):
    # Arrange
    clone = dirty_checkout["clone"]
    # Act
    content = (clone / "f.txt").read_text()
    # Assert
    assert content == "local uncommitted edit"


# -- off-develop checkout (skip) ------------------------------------------


@pytest.fixture
def off_develop(tmp_path):
    _, clone = _make_origin_and_clone(tmp_path)
    _git(clone, "checkout", "-q", "-b", "feature/x")
    return _sync_one("pkg", {"local_path": str(clone)}, dry_run=False)


def test_off_develop_action_is_off_develop(off_develop):
    # Arrange
    row = off_develop
    # Act
    action = row["action"]
    # Assert
    assert action == "off-develop"


def test_off_develop_detail_names_branch(off_develop):
    # Arrange
    row = off_develop
    # Act
    detail = row["detail"]
    # Assert
    assert "feature/x" in detail


# -- diverged develop (skip, never force) ---------------------------------


@pytest.fixture
def diverged(tmp_path):
    origin, clone = _make_origin_and_clone(tmp_path)
    _advance_origin(tmp_path, origin, "origin-only")
    local_head = _commit(clone, "g.txt", "local-only")
    row = _sync_one("pkg", {"local_path": str(clone)}, dry_run=False)
    return {"row": row, "clone": clone, "local_head": local_head}


def test_diverged_action_is_diverged(diverged):
    # Arrange
    row = diverged["row"]
    # Act
    action = row["action"]
    # Assert
    assert action == "diverged"


def test_diverged_preserves_local_commit(diverged):
    # Arrange
    clone, local_head = diverged["clone"], diverged["local_head"]
    # Act
    head = _git(clone, "rev-parse", "develop")
    # Assert
    assert head == local_head


# -- trivial states -------------------------------------------------------


def test_synced_checkout_is_noop(tmp_path):
    # Arrange
    _, clone = _make_origin_and_clone(tmp_path)
    # Act
    row = _sync_one("pkg", {"local_path": str(clone)}, dry_run=False)
    # Assert
    assert row["action"] == "synced"


def test_missing_checkout_is_reported(tmp_path):
    # Arrange
    missing = tmp_path / "nope"
    # Act
    row = _sync_one("pkg", {"local_path": str(missing)}, dry_run=False)
    # Assert
    assert row["action"] == "missing"


def test_emit_pulled_events_fires_only_for_actually_pulled_repos():
    # Arrange
    rows = [
        {"package": "scitex-io", "action": "pulled"},
        {"package": "scitex-cv", "action": "synced"},
        {"package": "scitex-db", "action": "would-pull"},
        {"package": "scitex-gists", "action": "diverged"},
    ]
    fired: list[str] = []
    # Act
    _emit_pulled_events(rows, emit_fn=fired.append)
    # Assert
    assert fired == ["scitex-io"]


def test_emit_pulled_events_is_silent_when_nothing_advanced():
    # Arrange
    rows = [{"package": "scitex-io", "action": "synced"}]
    fired: list[str] = []
    # Act
    _emit_pulled_events(rows, emit_fn=fired.append)
    # Assert
    assert fired == []
