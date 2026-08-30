#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The engine, against real repositories and real worktrees.

The three worktree shapes each get their own end-to-end test because
their difference is the whole safety argument: a cleanup that cannot
tell "abandoned" from "someone is mid-edit" is not safe to run daily
across seven hosts and roughly 180 repositories.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev.branch_hygiene import (
    DEFAULT_MAX_AGE_HOURS,
    DROP_MERGED,
    KEEP_WORKTREE_BUSY,
    align_checkout,
    sweep_local,
    sweep_repo,
)
from scitex_dev.branch_hygiene._probe import (
    current_branch,
    list_local_rows,
    worktree_map,
    worktree_touch_epoch,
)

from .conftest import ANCIENT_EPOCH, FUTURE_NOW, run_git


def no_prs(repo, state):
    """GitHub answered: this repository has no pull requests at all.

    A REAL answer, not a mock of the code under test — it stands in for
    the ``gh`` listing exactly as :mod:`scitex_dev.hygiene`'s own tests
    inject ``pr_merged`` / ``pr_open``. The fixture repositories have no
    remote, so the live lookup honestly returns ``None`` for every
    branch, every branch is kept as unknown, and the delete path is
    never reached. Distinguishing "GitHub said no" from "nobody
    answered" is the whole point of the predicate; the tests have to be
    able to say the first one.
    """
    del repo, state
    return set()


def open_pr_on(*names):
    """GitHub answered: these branches have an open pull request."""

    def lookup(repo, state):
        del repo
        return set(names) if state == "open" else set()

    return lookup


# ------------------------------------------------------------------ #
# Leg 1 — checkouts to develop.                                       #
# ------------------------------------------------------------------ #


def test_a_checkout_already_on_develop_is_left_alone(repo: Path):
    """No write, and it says so rather than reporting a switch."""
    # Arrange
    # Act
    result = align_checkout(repo, execute=True)
    # Assert
    assert result.action == "on-develop"


def test_a_clean_checkout_off_develop_is_switched(repo: Path):
    """The step that makes yesterday's topic branch collectable at all."""
    # Arrange
    run_git(repo, "checkout", "-q", "feat/unlanded")
    # Act
    align_checkout(repo, execute=True)
    # Assert
    assert current_branch(repo) == "develop"


def test_a_dirty_checkout_is_refused_and_stays_put(repo: Path):
    """Never stashed, never forced — this runs unattended once a day."""
    # Arrange
    run_git(repo, "checkout", "-q", "feat/unlanded")
    (repo / "scratch.txt").write_text("uncommitted\n")
    # Act
    result = align_checkout(repo, execute=True)
    # Assert
    assert (result.action, current_branch(repo)) == ("dirty", "feat/unlanded")


def test_a_dry_run_does_not_switch_the_checkout(repo: Path):
    """`would-switch` is a plan, and a plan writes nothing."""
    # Arrange
    run_git(repo, "checkout", "-q", "feat/unlanded")
    # Act
    align_checkout(repo, execute=False)
    # Assert
    assert current_branch(repo) == "feat/unlanded"


# ------------------------------------------------------------------ #
# Leg 2 — local branches.                                             #
# ------------------------------------------------------------------ #


def test_the_dry_run_deletes_nothing(repo: Path):
    """Both of the worst rules this sweep has carried were caught by a
    rehearsal, so the rehearsal must be the default and must be inert."""
    # Arrange
    before = list_local_rows(repo)[1]
    # Act
    sweep_local(repo, execute=False, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert list_local_rows(repo)[1] == before


def test_protected_names_survive_a_real_pass(repo: Path):
    """main / develop / BOTH CLA spellings, at 400 days old.

    `cla` and `cla-signatures` are both here because both are live
    signature stores in this org, carrying the identical
    `signatures/cla.json`. A pass that protects one spelling and
    collects the other is the original near-miss with the names
    swapped.
    """
    # Arrange
    # Act
    sweep_local(repo, execute=True, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert {"develop", "main", "cla", "cla-signatures"} <= {
        name for name, _, _ in list_local_rows(repo)[1]
    }


def test_a_stale_agent_branch_is_collected(repo: Path):
    """`claude/sweep-1` is the shape the too-broad `cla*` would have kept."""
    # Arrange
    # Act
    sweep_local(repo, execute=True, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert "claude/sweep-1" not in {name for name, _, _ in list_local_rows(repo)[1]}


def test_a_verified_bundle_is_written_before_any_delete(repo: Path):
    """Cheap insurance for the leg that removes work which never landed."""
    # Arrange
    # Act
    _, _, restore, _ = sweep_local(repo, execute=True, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert "branches.bundle" in restore


def test_a_wide_window_leaves_only_the_merged_drops(repo: Path):
    """MERGED IS NOT SUBJECT TO THE WINDOW, and this is where that shows.

    Widen the staleness window past every branch and the stale drops
    vanish — but `feat/landed` and `claude/sweep-1` are ancestors of
    develop, so they still go. That is rule (c) working: finished work
    goes however recently touched, which is also however LOOSELY the
    window is set.
    """
    # Arrange
    # Act
    verdicts, _, _, _ = sweep_local(
        repo, execute=True, now=FUTURE_NOW, max_age_hours=10**6, pr_heads=no_prs
    )
    # Assert
    assert {v.reason for v in verdicts if v.drop} == {DROP_MERGED}


def test_an_open_prs_head_survives_a_real_pass(repo: Path):
    """A 400-day-old branch with an OPEN pull request is work someone
    OWES, not work abandoned. Deleting it would close the PR."""
    # Arrange
    # Act
    sweep_local(
        repo,
        execute=True,
        now=FUTURE_NOW,
        pr_heads=open_pr_on("feat/unlanded"),
    )
    # Assert
    assert "feat/unlanded" in {name for name, _, _ in list_local_rows(repo)[1]}


# ------------------------------------------------------------------ #
# Leg 2b — the three worktree shapes.                                 #
# ------------------------------------------------------------------ #


def test_a_clean_worktree_is_removed_and_its_branch_deleted(
    repo_with_clean_worktree,
):
    """git's refusal is not a terminus: the worktree is stale too."""
    # Arrange
    repo, worktree = repo_with_clean_worktree
    # Act
    sweep_local(repo, execute=True, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert not worktree.exists()


def test_a_clean_worktrees_branch_is_gone_too(repo_with_clean_worktree):
    """Removing the tree without collecting the branch is half a sweep."""
    # Arrange
    repo, _ = repo_with_clean_worktree
    # Act
    sweep_local(repo, execute=True, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert "feat/unlanded" not in {name for name, _, _ in list_local_rows(repo)[1]}


def test_a_recently_touched_dirty_worktree_survives(repo_with_dirty_worktree):
    """THE UNRECOVERABLE CASE, end to end. The branch's tip is ancient
    and the file was written a moment ago."""
    # Arrange
    repo, worktree = repo_with_dirty_worktree
    # Act
    sweep_local(repo, execute=True, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert (worktree / "in-progress.txt").exists()


def test_a_recently_touched_dirty_worktrees_branch_survives(
    repo_with_dirty_worktree,
):
    """Keep BOTH — the tree and the ref that finds it again."""
    # Arrange
    repo, _ = repo_with_dirty_worktree
    # Act
    sweep_local(repo, execute=True, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert "feat/unlanded" in {name for name, _, _ in list_local_rows(repo)[1]}


def test_a_recently_touched_dirty_worktree_says_why(repo_with_dirty_worktree):
    """A silent keep cannot be told from a keep nobody decided."""
    # Arrange
    repo, _ = repo_with_dirty_worktree
    # Act
    verdicts, _, _, _ = sweep_local(repo, execute=True, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert KEEP_WORKTREE_BUSY in {v.reason for v in verdicts}


def test_an_abandoned_dirty_worktree_is_forced_away(
    repo_with_abandoned_worktree,
):
    """Uncommitted AND untouched past the window is orphaned garbage."""
    # Arrange
    repo, worktree = repo_with_abandoned_worktree
    # Act
    sweep_local(repo, execute=True, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert not worktree.exists()


def test_a_forced_removal_names_the_files_it_discarded(
    repo_with_abandoned_worktree,
):
    """Forcing is authorised; forcing SILENTLY is not."""
    # Arrange
    repo, _ = repo_with_abandoned_worktree
    # Act
    _, discarded, _, _ = sweep_local(repo, execute=True, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert any("abandoned.txt" in entry for d in discarded for entry in d.entries)


def test_a_forced_removal_names_the_worktree_path(
    repo_with_abandoned_worktree,
):
    """So a human can go and look at what was taken."""
    # Arrange
    repo, worktree = repo_with_abandoned_worktree
    # Act
    _, discarded, _, _ = sweep_local(repo, execute=True, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert [d.path for d in discarded] == [str(worktree)]


def test_the_worktree_shapes_are_measured_on_the_files_not_the_branch(
    repo_with_dirty_worktree,
):
    """The instrument, stated as its own fact: the dirty tree's newest
    file is far younger than the branch's ancient tip commit."""
    # Arrange
    _, worktree = repo_with_dirty_worktree
    # Act
    newest = worktree_touch_epoch(worktree)
    # Assert
    assert newest > float(ANCIENT_EPOCH)


# ------------------------------------------------------------------ #
# The whole pass, and the flags that select its legs.                 #
# ------------------------------------------------------------------ #


def test_sweep_repo_reports_the_repository_it_could_not_read(tmp_path: Path):
    """An unreadable repo reports zero candidates exactly like a clean
    one, so it has to name itself instead."""
    # Arrange
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    # Act
    result = sweep_repo(empty)
    # Assert
    assert result.unreadable is True


def test_no_local_leaves_the_local_branches_untouched(repo: Path):
    """`--no-local` is what lets the remote leg run on one host alone."""
    # Arrange
    before = list_local_rows(repo)[1]
    # Act
    sweep_repo(repo, execute=True, do_local=False, now=FUTURE_NOW, pr_heads=no_prs)
    # Assert
    assert list_local_rows(repo)[1] == before


def test_the_primary_checkouts_branch_is_seen_as_primary(repo: Path):
    """The map that keeps the sweep from deleting its own repository."""
    # Arrange
    # Act
    mapping = worktree_map(repo)
    # Assert
    assert mapping["develop"][1] is True


def test_the_default_window_is_one_day():
    """The operator's rule, pinned where a reader will look for it."""
    # Arrange
    # Act
    window = DEFAULT_MAX_AGE_HOURS
    # Assert
    assert window == 24.0


# EOF
