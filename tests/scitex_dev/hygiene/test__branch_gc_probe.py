#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Observation, on a real repository. Every failure must become an UNKNOWN."""

from __future__ import annotations

from .conftest import run_git

from scitex_dev.hygiene._branch_gc_probe import (
    branch_sha,
    commit_epoch,
    head_branch_names,
    is_ancestor_of_base,
    list_local_branches,
    origin_head_branch,
    patch_equivalent_to_base,
    reflog_epoch,
    run_git as probe_git,
)


def test_list_local_branches_enumerates_refs_heads(repo):
    # Arrange
    # Act
    ok, infos, _ = list_local_branches(repo)
    # Assert
    assert ok and {info.name for info in infos} >= {"develop", "main", "release/1.0"}


def test_list_local_branches_reports_a_sha_for_every_branch(repo):
    # Arrange
    # Act
    _, infos, _ = list_local_branches(repo)
    # Assert
    assert all(len(info.sha) == 40 for info in infos)


def test_list_local_branches_never_returns_a_tag(repo):
    """Scoped by the ref pattern itself, so tags are structurally out of reach."""
    # Arrange
    run_git(repo, "tag", "v1.0")
    # Act
    _, infos, _ = list_local_branches(repo)
    # Assert
    assert "v1.0" not in {info.name for info in infos}


def test_unreadable_repo_is_not_ok(tmp_path):
    """A non-repo is UNKNOWN, never "a repo with no branches"."""
    # Arrange
    plain = tmp_path / "plain"
    plain.mkdir()
    # Act
    ok, _, _ = list_local_branches(plain)
    # Assert
    assert ok is False


def test_head_branch_names_includes_the_main_checkout_head(repo):
    # Arrange
    # Act
    heads = head_branch_names(repo)
    # Assert
    assert heads == {"develop"}


def test_head_branch_names_includes_a_linked_worktree_head(repo, tmp_path):
    # Arrange
    run_git(repo, "worktree", "add", str(tmp_path / "wt"), "feature/picked")
    # Act
    heads = head_branch_names(repo)
    # Assert
    assert "feature/picked" in heads


def test_head_branch_names_is_none_for_an_unreadable_repo(tmp_path):
    # Arrange
    plain = tmp_path / "plain"
    plain.mkdir()
    # Act
    # Assert
    assert head_branch_names(plain) is None


def test_ancestor_check_reports_the_base_was_evaluated(repo):
    """The `evaluated` flag is what licenses a definite NOT-LANDED."""
    # Arrange
    # Act
    _, evaluated = is_ancestor_of_base(repo, "feature/unlanded", "develop")
    # Assert
    assert evaluated is True


def test_missing_base_is_not_evaluated(repo):
    """A base we never read must not contribute to any verdict."""
    # Arrange
    # Act
    landed, evaluated = is_ancestor_of_base(repo, "feature/unlanded", "no-such-base")
    # Assert
    assert (landed, evaluated) == (None, False)


def test_patch_equivalence_sees_a_cherry_picked_landing(repo):
    # Arrange
    # Act
    landed, _ = patch_equivalent_to_base(repo, "feature/picked", "develop")
    # Assert
    assert landed is True


def test_patch_equivalence_is_blind_to_a_multi_commit_squash(repo):
    """The documented limit, pinned so nobody later assumes it is enough."""
    # Arrange
    # Act
    landed, _ = patch_equivalent_to_base(repo, "feature/squashed", "develop")
    # Assert
    assert landed is False


def test_commit_epoch_reads_the_committer_time(repo):
    # Arrange
    # Act
    epoch = commit_epoch(repo, "feature/landed-ff")
    # Assert
    assert epoch == 1000000010.0


def test_commit_epoch_is_none_for_a_missing_ref(repo):
    # Arrange
    # Act
    # Assert
    assert commit_epoch(repo, "no/such/branch") is None


def test_reflog_epoch_reads_when_the_ref_last_moved_here(repo):
    """The second age signal — a NEW ref off an ancient base reads as new."""
    # Arrange
    # Act
    epoch = reflog_epoch(repo, "relocation/residency")
    # Assert — created seconds ago, far newer than the 2001 commit it points at.
    assert epoch is not None and epoch > 1600000000


def test_branch_sha_matches_rev_parse(repo):
    # Arrange
    expected = run_git(repo, "rev-parse", "feature/landed-ff")
    # Act
    # Assert
    assert branch_sha(repo, "feature/landed-ff") == expected


def test_branch_sha_is_none_for_a_missing_branch(repo):
    # Arrange
    # Act
    # Assert
    assert branch_sha(repo, "no/such/branch") is None


def test_origin_head_is_none_without_a_remote(repo):
    """No remote means UNKNOWN default branch — not "there isn't one"."""
    # Arrange
    # Act
    # Assert
    assert origin_head_branch(repo) is None


def test_run_git_degrades_to_false_instead_of_raising(tmp_path):
    """An unreadable cwd must never crash a scheduled pass."""
    # Arrange
    # Act
    ok, _ = probe_git(tmp_path / "does-not-exist", "status")
    # Assert
    assert ok is False


# EOF
