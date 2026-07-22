#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for distribution-identity enumeration (``_ecosystem._enumerate``).

These exercise REAL git repositories created under ``tmp_path`` — no
mocks. Identity is read from the origin remote, so a test that faked the
remote would prove nothing about the thing under test.

The suite is deliberately two-armed. The collapse arm proves duplicate
checkouts / worktrees fold into ONE distribution; the CONTROL arm
(``test_two_genuinely_distinct_repos_*``) proves the collapse is
selective and not "collapse everything", which would look like a fix
while destroying the enumeration.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scitex_dev._ecosystem._enumerate import (
    MEASURED_LOCAL_CHECKOUT,
    enumerate_distributions,
    normalize_remote,
    read_origin,
    scan_checkout_root,
)

IO_ORIGIN = "git@github.com:scitex-ai/scitex-io.git"
SAC_ORIGIN = "git@github.com:scitex-ai/scitex-agent-container.git"


# --------------------------------------------------------------------- #
# Real-git helpers + fixtures                                            #
# --------------------------------------------------------------------- #


def _git(path: Path, *args: str) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc


def _make_checkout(root: Path, dirname: str, origin: str) -> Path:
    """Create a real git checkout at ``root/dirname`` with ``origin`` set."""
    path = root / dirname
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    _git(path, "remote", "add", "origin", origin)
    (path / "README.md").write_text("x\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


@pytest.fixture
def duplicate_checkouts(tmp_path):
    """Two directories, one origin — the scitex-io / -dotscitex shape."""
    canonical = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    duplicate = _make_checkout(tmp_path, "scitex-io-dotscitex", IO_ORIGIN)
    return {
        "canonical": canonical,
        "duplicate": duplicate,
        "result": enumerate_distributions(paths=[str(canonical), str(duplicate)]),
    }


@pytest.fixture
def distinct_repos(tmp_path):
    """CONTROL ARM — two genuinely different repos, two distributions."""
    io = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    stats = _make_checkout(
        tmp_path, "scitex-stats", "git@github.com:scitex-ai/scitex-stats.git"
    )
    return {"result": enumerate_distributions(paths=[str(io), str(stats)])}


@pytest.fixture
def repo_with_worktree(tmp_path):
    """A main checkout plus a linked git worktree of the same repo."""
    main = _make_checkout(tmp_path, "scitex-agent-container", SAC_ORIGIN)
    worktree = tmp_path / "scitex-agent-container-wt-skills"
    _git(main, "worktree", "add", "-q", "-b", "wt-skills", str(worktree))
    return {
        "main": main,
        "worktree": worktree,
        "result": enumerate_distributions(paths=[str(main), str(worktree)]),
    }


@pytest.fixture
def org_delta(tmp_path):
    """One local checkout against a three-repo org listing."""
    io = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    org_repos = [
        "scitex-ai/scitex-io",
        "scitex-ai/scitex-storage",
        "scitex-ai/scitex-ghost",
    ]
    return {"result": enumerate_distributions(paths=[str(io)], org_repos=org_repos)}


# --------------------------------------------------------------------- #
# normalize_remote                                                       #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:scitex-ai/scitex-io.git",
        "https://github.com/scitex-ai/scitex-io.git",
        "https://github.com/scitex-ai/scitex-io",
        "ssh://git@github.com/scitex-ai/scitex-io.git",
        "https://github.com/scitex-ai/scitex-io/",
    ],
    ids=["scp", "https-dotgit", "https", "ssh", "trailing-slash"],
)
def test_every_url_spelling_of_one_repo_normalizes_to_one_identity(url):
    # Arrange
    expected = "scitex-ai/scitex-io"
    # Act
    identity = normalize_remote(url)
    # Assert
    assert identity == expected


def test_blank_remote_url_normalizes_to_none_rather_than_a_guess():
    # Arrange
    url = "   "
    # Act
    identity = normalize_remote(url)
    # Assert
    assert identity is None


def test_two_different_repos_normalize_to_different_identities():
    # Arrange
    first = "git@github.com:scitex-ai/scitex-io.git"
    second = "git@github.com:scitex-ai/scitex-stats.git"
    # Act
    identities = {normalize_remote(first), normalize_remote(second)}
    # Assert
    assert len(identities) == 2


# --------------------------------------------------------------------- #
# (b) DOUBLE-COUNTING — duplicate checkouts collapse into aliases        #
# --------------------------------------------------------------------- #


def test_two_directories_sharing_one_origin_yield_one_distribution(
    duplicate_checkouts,
):
    # Arrange
    result = duplicate_checkouts["result"]
    # Act
    count = result.distribution_count
    # Assert
    assert count == 1


def test_two_directories_sharing_one_origin_report_that_repo_identity(
    duplicate_checkouts,
):
    # Arrange
    result = duplicate_checkouts["result"]
    # Act
    repos = [d.repo for d in result.distributions]
    # Assert
    assert repos == ["scitex-ai/scitex-io"]


def test_non_canonical_duplicate_checkout_is_reported_as_an_alias_not_dropped(
    duplicate_checkouts,
):
    # Arrange
    result = duplicate_checkouts["result"]
    # Act
    alias_paths = [a.path for a in result.distributions[0].aliases]
    # Assert
    assert alias_paths == [str(duplicate_checkouts["duplicate"])]


def test_duplicate_checkout_alias_is_labelled_duplicate_checkout(duplicate_checkouts):
    # Arrange
    result = duplicate_checkouts["result"]
    # Act
    reasons = [a.reason for a in result.distributions[0].aliases]
    # Assert
    assert reasons == ["duplicate-checkout"]


def test_collapsing_one_duplicate_reports_one_alias_collapsed(duplicate_checkouts):
    # Arrange
    result = duplicate_checkouts["result"]
    # Act
    collapsed = result.aliases_collapsed
    # Assert
    assert collapsed == 1


def test_canonical_checkout_is_the_directory_matching_the_repo_name(tmp_path):
    # Arrange — sorted order alone would pick the "aaa-" path first
    _make_checkout(tmp_path, "aaa-scitex-io-clone", IO_ORIGIN)
    canonical = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    paths = [str(tmp_path / "aaa-scitex-io-clone"), str(canonical)]
    # Act
    result = enumerate_distributions(paths=paths)
    # Assert
    assert result.distributions[0].canonical_path == str(canonical)


def test_canonical_falls_back_to_first_sorted_path_when_no_name_matches(tmp_path):
    # Arrange
    first = _make_checkout(tmp_path, "aaa-clone", IO_ORIGIN)
    _make_checkout(tmp_path, "zzz-clone", IO_ORIGIN)
    paths = [str(tmp_path / "zzz-clone"), str(first)]
    # Act
    result = enumerate_distributions(paths=paths)
    # Assert
    assert result.distributions[0].canonical_path == str(first)


# --------------------------------------------------------------------- #
# CONTROL ARM — distinct repos must NOT collapse                         #
# --------------------------------------------------------------------- #


def test_two_genuinely_distinct_repos_are_counted_as_two_distributions(distinct_repos):
    # Arrange
    result = distinct_repos["result"]
    # Act
    count = result.distribution_count
    # Assert
    assert count == 2


def test_two_genuinely_distinct_repos_keep_both_repo_identities(distinct_repos):
    # Arrange
    result = distinct_repos["result"]
    # Act
    repos = {d.repo for d in result.distributions}
    # Assert
    assert repos == {"scitex-ai/scitex-io", "scitex-ai/scitex-stats"}


def test_two_genuinely_distinct_repos_collapse_no_aliases(distinct_repos):
    # Arrange
    result = distinct_repos["result"]
    # Act
    collapsed = result.aliases_collapsed
    # Assert
    assert collapsed == 0


# --------------------------------------------------------------------- #
# Worktrees                                                              #
# --------------------------------------------------------------------- #


def test_git_worktree_of_a_counted_repo_is_not_a_separate_distribution(
    repo_with_worktree,
):
    # Arrange
    result = repo_with_worktree["result"]
    # Act
    count = result.distribution_count
    # Assert
    assert count == 1


def test_worktree_collapse_still_reports_both_directories_as_scanned(
    repo_with_worktree,
):
    # Arrange
    result = repo_with_worktree["result"]
    # Act
    scanned = result.directories_scanned
    # Assert
    assert scanned == 2


def test_git_worktree_is_reported_as_an_alias_labelled_worktree(repo_with_worktree):
    # Arrange
    result = repo_with_worktree["result"]
    # Act
    aliases = [(a.path, a.reason) for a in result.distributions[0].aliases]
    # Assert
    assert aliases == [(str(repo_with_worktree["worktree"]), "worktree")]


def test_worktree_never_wins_canonical_even_when_its_name_matches_the_repo(tmp_path):
    # Arrange — the worktree directory is named exactly like the repo
    main = _make_checkout(tmp_path, "checkout-a", IO_ORIGIN)
    worktree = tmp_path / "scitex-io"
    _git(main, "worktree", "add", "-q", "-b", "feature", str(worktree))
    # Act
    result = enumerate_distributions(paths=[str(main), str(worktree)])
    # Assert
    assert result.distributions[0].canonical_path == str(main)


# --------------------------------------------------------------------- #
# (a) OMISSION — org repos with no local checkout                        #
# --------------------------------------------------------------------- #


def test_org_repo_with_no_local_checkout_is_present_in_the_output(org_delta):
    # Arrange
    result = org_delta["result"]
    # Act
    repos = {d.repo for d in result.distributions}
    # Assert
    assert "scitex-ai/scitex-storage" in repos


def test_org_repo_with_no_local_checkout_is_flagged_not_checked_out(org_delta):
    # Arrange
    result = org_delta["result"]
    # Act
    storage = [
        d for d in result.distributions if d.repo == "scitex-ai/scitex-storage"
    ][0]
    # Assert
    assert storage.checked_out is False


def test_org_repo_with_no_local_checkout_has_no_canonical_path(org_delta):
    # Arrange
    result = org_delta["result"]
    # Act
    storage = [
        d for d in result.distributions if d.repo == "scitex-ai/scitex-storage"
    ][0]
    # Assert
    assert storage.canonical_path is None


def test_not_checked_out_count_is_reported_in_the_counts_block(org_delta):
    # Arrange
    payload = org_delta["result"].to_dict()
    # Act
    not_checked_out = payload["counts"]["not_checked_out"]
    # Assert
    assert not_checked_out == 2


def test_omitting_the_org_listing_is_labelled_unavailable_not_an_empty_delta(tmp_path):
    # Arrange
    io = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    # Act
    result = enumerate_distributions(paths=[str(io)])
    # Assert
    assert result.org_listing_available is False


def test_locally_checked_out_repo_absent_from_org_listing_is_flagged_not_in_org(
    tmp_path,
):
    # Arrange
    fig = _make_checkout(tmp_path, "figrecipe", "git@github.com:someone/figrecipe.git")
    # Act
    result = enumerate_distributions(
        paths=[str(fig)], org_repos=["scitex-ai/scitex-io"]
    )
    # Assert
    assert result.distributions[0].in_org is False


# --------------------------------------------------------------------- #
# Error surfacing — degradation must be loud                             #
# --------------------------------------------------------------------- #


def test_directory_without_an_origin_remote_yields_no_distribution(tmp_path):
    # Arrange
    path = tmp_path / "no-remote"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    # Act
    result = enumerate_distributions(paths=[str(path)])
    # Assert
    assert result.distribution_count == 0


def test_directory_without_an_origin_remote_is_recorded_as_an_error(tmp_path):
    # Arrange
    path = tmp_path / "no-remote"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    # Act
    result = enumerate_distributions(paths=[str(path)])
    # Assert
    assert len(result.errors) == 1


def test_directory_without_an_origin_remote_is_listed_as_unresolved(tmp_path):
    # Arrange
    path = tmp_path / "no-remote"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    # Act
    result = enumerate_distributions(paths=[str(path)])
    # Assert
    assert result.unresolved_paths == [str(path)]


def test_unreadable_path_still_counts_toward_directories_scanned(tmp_path):
    # Arrange
    good = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    missing = tmp_path / "does-not-exist"
    # Act
    payload = enumerate_distributions(paths=[str(good), str(missing)]).to_dict()
    # Assert
    assert payload["counts"]["directories_scanned"] == 2


def test_unreadable_path_is_counted_as_an_error_not_silently_dropped(tmp_path):
    # Arrange
    good = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    missing = tmp_path / "does-not-exist"
    # Act
    payload = enumerate_distributions(paths=[str(good), str(missing)]).to_dict()
    # Assert
    assert payload["counts"]["errors"] == 1


def test_read_origin_returns_an_error_string_for_a_non_directory(tmp_path):
    # Arrange
    missing = tmp_path / "nope"
    # Act
    _repo, error = read_origin(missing)
    # Assert
    assert "not a directory" in error


def test_org_listing_failure_is_appended_to_errors(tmp_path):
    # Arrange
    io = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    # Act
    result = enumerate_distributions(
        paths=[str(io)], org_error="gh repo list scitex-ai exited 4"
    )
    # Assert
    assert any("gh repo list" in e for e in result.errors)


# --------------------------------------------------------------------- #
# (c) STALENESS / labelling                                              #
# --------------------------------------------------------------------- #


def test_result_states_which_tree_was_measured(tmp_path):
    # Arrange
    io = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    # Act
    result = enumerate_distributions(paths=[str(io)])
    # Assert
    assert result.measured_tree == MEASURED_LOCAL_CHECKOUT


def test_measured_tree_label_names_local_checkouts_explicitly(tmp_path):
    # Arrange
    io = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    # Act
    payload = enumerate_distributions(paths=[str(io)]).to_dict()
    # Assert
    assert "local-checkouts" in payload["measured_tree"]


def test_json_payload_declares_that_it_counts_distributions(tmp_path):
    # Arrange
    io = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    # Act
    payload = enumerate_distributions(paths=[str(io)]).to_dict()
    # Assert
    assert payload["kind"] == "distributions"


def test_json_counts_block_separates_directories_from_distributions(tmp_path):
    # Arrange
    io = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    # Act
    payload = enumerate_distributions(paths=[str(io)]).to_dict()
    # Assert
    assert set(payload["counts"]) == {
        "directories_scanned",
        "distributions",
        "aliases_collapsed",
        "not_checked_out",
        "errors",
    }


def test_summary_line_states_distributions_over_directories(duplicate_checkouts):
    # Arrange
    result = duplicate_checkouts["result"]
    # Act
    line = result.summary_line()
    # Assert
    assert "1 distribution(s) from 2 director(ies)" in line


def test_summary_line_states_how_many_aliases_were_collapsed(duplicate_checkouts):
    # Arrange
    result = duplicate_checkouts["result"]
    # Act
    line = result.summary_line()
    # Assert
    assert "1 alias(es) collapsed" in line


def test_summary_line_states_the_measured_tree(duplicate_checkouts):
    # Arrange
    result = duplicate_checkouts["result"]
    # Act
    line = result.summary_line()
    # Assert
    assert "Measured tree:" in line


# --------------------------------------------------------------------- #
# Directory-scan input — the shape brand-wide sweeps actually use        #
# --------------------------------------------------------------------- #


def test_scan_checkout_root_finds_every_git_checkout_under_the_root(tmp_path):
    # Arrange
    _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    _make_checkout(tmp_path, "scitex-io-dotscitex", IO_ORIGIN)
    (tmp_path / "not-a-repo").mkdir()
    # Act
    found = scan_checkout_root(str(tmp_path))
    # Assert
    assert found == [
        str(tmp_path / "scitex-io"),
        str(tmp_path / "scitex-io-dotscitex"),
    ]


def test_scan_checkout_root_of_a_missing_directory_returns_empty(tmp_path):
    # Arrange
    missing = tmp_path / "nope"
    # Act
    found = scan_checkout_root(str(missing))
    # Assert
    assert found == []


def test_directory_scan_of_duplicate_checkouts_yields_one_distribution(tmp_path):
    # Arrange — the ~/proj shape: two dirs, one repo
    _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    _make_checkout(tmp_path, "scitex-io-dotscitex", IO_ORIGIN)
    # Act
    result = enumerate_distributions(paths=scan_checkout_root(str(tmp_path)))
    # Assert
    assert result.distribution_count == 1


def test_orphaned_worktree_error_names_the_worktree_failure_explicitly(tmp_path):
    # Arrange — a linked worktree whose main checkout has been removed
    import shutil

    main = _make_checkout(tmp_path, "scitex-io", IO_ORIGIN)
    worktree = tmp_path / "scitex-io-feature"
    _git(main, "worktree", "add", "-q", "-b", "feature", str(worktree))
    shutil.rmtree(main)
    # Act
    result = enumerate_distributions(paths=[str(worktree)])
    # Assert
    assert any("orphaned-worktree" in e for e in result.errors)


# EOF
