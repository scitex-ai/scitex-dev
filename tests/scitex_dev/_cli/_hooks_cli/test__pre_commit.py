#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The local-``main``-is-a-mirror guard, exercised in BOTH directions.

An enforcement that has only ever seen the compliant case has never been
tested: a hook that exits 0 unconditionally passes every "a topic branch
still commits" test ever written. So the refusal is proved by attempting
a real commit on ``main`` in a real repository with the hook really
wired, and the permission is proved the same way on a topic branch.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli._hooks_cli import register_hooks_commands
from scitex_dev._cli._hooks_cli._hookspath import (
    CONFIGURED,
    FORCED,
    HOOKS_DIR,
    NO_GIT,
    REFUSED,
    WIRED,
    plan_hookspath,
    read_hookspath,
)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(
        {
            "GIT_CONFIG_GLOBAL": str(repo / ".gitconfig-none"),
            "GIT_CONFIG_SYSTEM": str(repo / ".gitconfig-none"),
        }
    )
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def cli():
    @click.group()
    def main():
        pass

    register_hooks_commands(main)
    return main


@pytest.fixture
def guarded_repo(tmp_path: Path, cli) -> Path:
    """A real repository with the guard really installed and wired."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    git(repo, "checkout", "-q", "-b", "main")
    (repo / "seed.txt").write_text("seed\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")
    CliRunner().invoke(
        cli, ["hooks", "enable-pre-commit", "--target", str(repo), "--yes"]
    )
    return repo


def _attempt_commit(repo: Path, message: str) -> subprocess.CompletedProcess:
    (repo / f"{message}.txt").write_text(f"{message}\n")
    git(repo, "add", "-A")
    return git(repo, "commit", "-m", message)


# ------------------------------------------------------------------ #
# Installation.                                                       #
# ------------------------------------------------------------------ #


def test_the_guard_is_deployed_as_a_symlink_named_pre_commit(guarded_repo: Path):
    """git's hook contract is filename-based; a `.sh` suffix never runs."""
    # Arrange
    # Act
    deployed = guarded_repo / ".githooks" / "pre-commit"
    # Assert
    assert deployed.is_symlink()


def test_installing_also_wires_core_hookspath(guarded_repo: Path):
    """Without this the hook is present, executable, and inert."""
    # Arrange
    # Act
    configured = read_hookspath(guarded_repo)
    # Assert
    assert configured == HOOKS_DIR


def test_a_dry_run_installs_nothing(tmp_path: Path, cli):
    """audit-cli §2 — every mutating verb exposes a --dry-run that writes
    nothing at all, not one that writes 'only the safe half'."""
    # Arrange
    repo = tmp_path / "dry"
    repo.mkdir()
    git(repo, "init", "-q")
    # Act
    CliRunner().invoke(
        cli,
        ["hooks", "enable-pre-commit", "--target", str(repo), "--dry-run"],
    )
    # Assert
    assert not (repo / ".githooks" / "pre-commit").exists()


# ------------------------------------------------------------------ #
# BOTH DIRECTIONS. Neither of these is redundant.                     #
# ------------------------------------------------------------------ #


def test_a_commit_on_main_is_refused(guarded_repo: Path):
    """DIRECTION 1. The whole point of the guard."""
    # Arrange
    # Act
    result = _attempt_commit(guarded_repo, "on-main")
    # Assert
    assert result.returncode != 0


def test_the_refusal_names_the_road_rather_than_only_saying_no(
    guarded_repo: Path,
):
    """A developer who hits this must be able to read the correct
    sequence out of the error instead of going to look for it."""
    # Arrange
    # Act
    result = _attempt_commit(guarded_repo, "explain")
    # Assert
    assert "PR into origin/develop" in result.stderr


def test_a_commit_on_master_is_refused_too(guarded_repo: Path):
    """Several repositories on the fleet still spell it `master`."""
    # Arrange
    git(guarded_repo, "checkout", "-q", "-b", "master")
    # Act
    result = _attempt_commit(guarded_repo, "on-master")
    # Assert
    assert result.returncode != 0


def test_a_commit_on_a_topic_branch_is_allowed(guarded_repo: Path):
    """DIRECTION 2. A guard that refuses everything is not a guard, and
    a guard that has only seen the refusal has not been tested."""
    # Arrange
    git(guarded_repo, "checkout", "-q", "-b", "feat/topic")
    # Act
    result = _attempt_commit(guarded_repo, "on-topic")
    # Assert
    assert result.returncode == 0


def test_a_commit_on_develop_is_allowed(guarded_repo: Path):
    """develop is step 1 of the road, not a place to be blocked."""
    # Arrange
    git(guarded_repo, "checkout", "-q", "-b", "develop")
    # Act
    result = _attempt_commit(guarded_repo, "on-develop")
    # Assert
    assert result.returncode == 0


def test_the_env_escape_hatch_lets_a_deliberate_commit_through(
    guarded_repo: Path,
):
    """Safe-by-default, not no-escape — and it prints a notice."""
    # Arrange
    (guarded_repo / "deliberate.txt").write_text("deliberate\n")
    git(guarded_repo, "add", "-A")
    env = dict(os.environ)
    env.update(
        {
            "SCITEX_DEV_ALLOW_MAIN_COMMIT": "1",
            "GIT_CONFIG_GLOBAL": str(guarded_repo / ".gitconfig-none"),
            "GIT_CONFIG_SYSTEM": str(guarded_repo / ".gitconfig-none"),
        }
    )
    # Act
    result = subprocess.run(
        ["git", "-C", str(guarded_repo), "commit", "-m", "deliberate"],
        capture_output=True,
        text=True,
        env=env,
    )
    # Assert
    assert result.returncode == 0


def test_no_verify_still_works(guarded_repo: Path):
    """git's own escape hatch is deliberately not disabled."""
    # Arrange
    (guarded_repo / "bypass.txt").write_text("bypass\n")
    git(guarded_repo, "add", "-A")
    # Act
    result = git(guarded_repo, "commit", "--no-verify", "-m", "bypass")
    # Assert
    assert result.returncode == 0


# ------------------------------------------------------------------ #
# The shared core.hooksPath rule — additive, then refuse.             #
# ------------------------------------------------------------------ #


def test_an_unset_hookspath_is_configured():
    """The ordinary case."""
    # Arrange
    # Act
    planned = plan_hookspath("", force=False)
    # Assert
    assert planned == CONFIGURED


def test_our_own_hookspath_is_a_no_op():
    """Re-running the installer must not churn the config."""
    # Arrange
    # Act
    planned = plan_hookspath(HOOKS_DIR, force=False)
    # Assert
    assert planned == WIRED


def test_someone_elses_hookspath_is_refused():
    """An operator who pointed it somewhere made a decision."""
    # Arrange
    # Act
    planned = plan_hookspath(".my-hooks", force=False)
    # Assert
    assert planned == REFUSED


def test_someone_elses_hookspath_yields_to_force():
    """Refusal is the default, not a wall."""
    # Arrange
    # Act
    planned = plan_hookspath(".my-hooks", force=True)
    # Assert
    assert planned == FORCED


def test_a_missing_git_is_not_reported_as_unset():
    """Collapsing those two would try to configure a machine with no git."""
    # Arrange
    # Act
    planned = plan_hookspath(None, force=False)
    # Assert
    assert planned == NO_GIT


# EOF
