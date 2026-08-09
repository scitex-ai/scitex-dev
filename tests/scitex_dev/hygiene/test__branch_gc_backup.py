#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The bundle-before-delete contract, on real bundles."""

from __future__ import annotations

from pathlib import Path

from .conftest import run_git

from scitex_dev.hygiene._branch_gc_backup import (
    create_backup,
    restore_command_for,
    sha_still_matches,
)
from scitex_dev.hygiene._branch_gc_model import BranchInfo


def _infos(repo, *names) -> list[BranchInfo]:
    return [
        BranchInfo(name=name, sha=run_git(repo, "rev-parse", name)) for name in names
    ]


def test_backup_of_an_empty_set_is_refused(repo):
    """No branches means no bundle — and the caller must not read it as ok."""
    # Arrange
    # Act
    result = create_backup(repo, [])
    # Assert
    assert result.ok is False


def test_backup_creates_a_non_empty_bundle(repo):
    # Arrange
    infos = _infos(repo, "feature/landed-ff")
    # Act
    result = create_backup(repo, infos)
    # Assert
    assert Path(result.bundle_path).stat().st_size > 0


def test_backup_verifies_the_bundle_before_reporting_ok(repo):
    """`ok` means VERIFIED, not merely written."""
    # Arrange
    infos = _infos(repo, "feature/landed-ff")
    # Act
    result = create_backup(repo, infos)
    # Assert
    assert result.ok is True


def test_backup_writes_a_manifest_beside_the_bundle(repo):
    # Arrange
    infos = _infos(repo, "feature/landed-ff")
    # Act
    result = create_backup(repo, infos)
    # Assert
    assert Path(result.manifest_path).is_file()


def test_backup_records_the_restore_command(repo):
    # Arrange
    infos = _infos(repo, "feature/landed-ff")
    # Act
    result = create_backup(repo, infos)
    # Assert
    assert "refs/heads/*:refs/heads/*" in result.restore_command


def test_backup_lands_under_the_repo_runtime_quarantine(repo):
    """Same convention as `ecosystem clean-root`; gitignored by default."""
    # Arrange
    infos = _infos(repo, "feature/landed-ff")
    # Act
    result = create_backup(repo, infos)
    # Assert
    assert ".scitex/dev/runtime/branch-gc/" in Path(result.bundle_path).as_posix()


def test_bundle_is_self_contained_and_verifies_in_a_fresh_clone(repo, tmp_path):
    """No `^base` thinning: a bundle that needs its base is unrestorable
    in exactly the situation a restore happens in."""
    # Arrange
    infos = _infos(repo, "feature/landed-ff")
    result = create_backup(repo, infos)
    fresh = tmp_path / "fresh"
    run_git(repo.parent, "init", "-q", str(fresh))
    # Act — fetch into an EMPTY repo; a thinned bundle cannot survive this.
    run_git(fresh, "fetch", result.bundle_path, "refs/heads/*:refs/heads/*")
    # Assert
    assert run_git(fresh, "rev-parse", "feature/landed-ff") == infos[0].sha


def test_restore_command_names_the_repo_and_the_bundle():
    # Arrange
    # Act
    command = restore_command_for("/repo", "/repo/.scitex/x/branches.bundle")
    # Assert
    assert command.startswith("git -C /repo fetch /repo/.scitex/x/branches.bundle")


def test_sha_still_matches_is_true_for_an_unmoved_branch(repo):
    """POSITIVE CONTROL for the re-confirmation step."""
    # Arrange
    sha = run_git(repo, "rev-parse", "feature/landed-ff")
    # Act
    # Assert
    assert sha_still_matches(repo, "feature/landed-ff", sha) is True


def test_sha_still_matches_is_false_after_the_branch_moves(repo):
    """Someone pushed during the pass — the bundle is now short."""
    # Arrange
    sha = run_git(repo, "rev-parse", "feature/landed-ff")
    run_git(repo, "branch", "-f", "feature/landed-ff", "feature/unlanded")
    # Act
    # Assert
    assert sha_still_matches(repo, "feature/landed-ff", sha) is False


def test_sha_still_matches_is_false_for_a_missing_branch(repo):
    """A branch that vanished is not "unchanged"."""
    # Arrange
    # Act
    # Assert
    assert sha_still_matches(repo, "no/such/branch", "deadbeef") is False


# EOF
