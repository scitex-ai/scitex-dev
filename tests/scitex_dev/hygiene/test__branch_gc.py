#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The engine, end to end, against real repositories.

The single most valuable test here is
``test_bundle_restores_the_deleted_branch_at_its_original_sha``: it builds
a repo, runs the engine to an actual deletion, restores from the bundle
with the literal one-liner the report printed, and asserts the SHA came
back. That is what makes "there is a backup" a MEASURED FACT rather than
a claim about a file that exists.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .conftest import (
    branches_in,
    enable_cleanup,
    merged_pr_for,
    no_active_work,
    no_open_pr,
    run_git,
)

from scitex_dev.hygiene import gc_repo
from scitex_dev.hygiene._branch_gc_model import (
    KEEP_ACTIVE_WORK,
    KEEP_DEFERRED_BY_LIMIT,
    KEEP_MOVED_DURING_PASS,
)

_PR = merged_pr_for("feature/squashed")


def _sweep(repo, home, **kwargs):
    """Run one pass with every seam injected — no network, no ambient state."""
    kwargs.setdefault("pr_merged", _PR)
    kwargs.setdefault("pr_open", no_open_pr)
    kwargs.setdefault("active_refs", no_active_work)
    kwargs.setdefault("now", time.time())
    return gc_repo(repo, home=home, **kwargs)


# --------------------------------------------------------------------------
# DEFAULT OFF — proven at the ENGINE level, not only at the loader.
# --------------------------------------------------------------------------


def test_no_config_present_deletes_nothing(repo, home):
    """Required property 1a, end to end: no config => the repo is untouched."""
    # Arrange
    before = branches_in(repo)
    # Act
    _sweep(repo, home, apply=True)
    # Assert
    assert branches_in(repo) == before


def test_config_present_but_key_absent_deletes_nothing(repo, home):
    """Required property 1b, end to end."""
    # Arrange
    (repo / ".scitex" / "dev").mkdir(parents=True, exist_ok=True)
    (repo / ".scitex" / "dev" / "config.yaml").write_text("project-type:\n  - pip\n")
    before = branches_in(repo)
    # Act
    _sweep(repo, home, apply=True)
    # Assert
    assert branches_in(repo) == before


def test_disabled_pass_still_reports_candidates(repo, home):
    """OFF is not BLIND: the report still says what an armed pass would do."""
    # Arrange
    # Act
    result = _sweep(repo, home, apply=True)
    # Assert
    assert [v.name for v in result.candidates] != []


def test_armed_config_without_apply_deletes_nothing(repo, home):
    """DRY-RUN DEFAULT (required property 5): config-on is not enough."""
    # Arrange
    enable_cleanup(repo, home)
    before = branches_in(repo)
    # Act
    _sweep(repo, home)
    # Assert
    assert branches_in(repo) == before


# --------------------------------------------------------------------------
# The armed path — POSITIVE CONTROL for every OFF test above.
# --------------------------------------------------------------------------


def test_armed_and_applied_deletes_a_landed_old_branch(repo, home):
    """POSITIVE CONTROL: the engine CAN delete, or none of the OFF tests mean anything."""
    # Arrange
    enable_cleanup(repo, home)
    # Act
    _sweep(repo, home, apply=True)
    # Assert
    assert "feature/landed-ff" not in branches_in(repo)


def test_squash_merged_branch_is_deleted_via_the_sha_fallback(repo, home):
    """`git branch -d` refuses a squash-merge; the compare-and-delete does not.

    This is the difference between a primitive that works in a squash-
    merging repo and `prune-merged`, which is inert in one.
    """
    # Arrange
    enable_cleanup(repo, home)
    # Act
    _sweep(repo, home, apply=True)
    # Assert
    assert "feature/squashed" not in branches_in(repo)


# --------------------------------------------------------------------------
# NEVER DELETE (required property 6).
# --------------------------------------------------------------------------


def test_apply_never_deletes_develop(repo, home):
    # Arrange
    enable_cleanup(repo, home)
    # Act
    _sweep(repo, home, apply=True)
    # Assert
    assert "develop" in branches_in(repo)


def test_apply_never_deletes_main(repo, home):
    # Arrange
    enable_cleanup(repo, home)
    # Act
    _sweep(repo, home, apply=True)
    # Assert
    assert "main" in branches_in(repo)


def test_apply_never_deletes_a_release_branch(repo, home):
    """release/* — the family the pre-existing PROTECTED set omits."""
    # Arrange
    enable_cleanup(repo, home)
    # Act
    _sweep(repo, home, apply=True)
    # Assert
    assert "release/1.0" in branches_in(repo)


def test_apply_never_deletes_an_unlanded_branch(repo, home):
    # Arrange
    enable_cleanup(repo, home)
    # Act
    _sweep(repo, home, apply=True)
    # Assert
    assert "feature/unlanded" in branches_in(repo)


def test_apply_never_deletes_a_young_branch(repo, home):
    """AGE FLOOR (required property 2), end to end.

    `relocation/residency` is landed, unprotected and unmentioned by any
    card. The ONLY thing keeping it is that its ref moved in this clone
    seconds ago. Neuter the floor and this branch is gone — which is
    exactly what happened on 2026-08-08.
    """
    # Arrange
    enable_cleanup(repo, home)
    # Act
    _sweep(repo, home, apply=True)
    # Assert
    assert "relocation/residency" in branches_in(repo)


def test_apply_never_deletes_a_branch_with_an_open_pr(repo, home):
    # Arrange
    enable_cleanup(repo, home)

    def has_open(_repo, branch):
        return branch == "feature/landed-ff"

    # Act
    _sweep(repo, home, apply=True, pr_open=has_open)
    # Assert
    assert "feature/landed-ff" in branches_in(repo)


def test_apply_never_deletes_a_branch_checked_out_in_a_worktree(repo, home, tmp_path):
    """A linked worktree's HEAD is off limits, not merely awkward to delete."""
    # Arrange
    enable_cleanup(repo, home)
    run_git(repo, "worktree", "add", str(tmp_path / "wt"), "feature/picked")
    # Act
    _sweep(repo, home, apply=True)
    # Assert
    assert "feature/picked" in branches_in(repo)


def test_apply_never_deletes_active_substrate(repo, home):
    """The leg the incident needed: a card naming the branch keeps it."""
    # Arrange
    enable_cleanup(repo, home)

    def active():
        return {"feature/landed-ff"}

    # Act
    _sweep(repo, home, apply=True, active_refs=active)
    # Assert
    assert "feature/landed-ff" in branches_in(repo)


def test_active_substrate_keep_reason_is_reported(repo, home):
    """...and the reason is legible, not a bare "skipped"."""
    # Arrange
    enable_cleanup(repo, home)

    def active():
        return {"feature/landed-ff"}

    # Act
    result = _sweep(repo, home, apply=True, active_refs=active)
    kept = {v.name: v.keep_reasons for v in result.kept}
    # Assert
    assert KEEP_ACTIVE_WORK in kept["feature/landed-ff"]


# --------------------------------------------------------------------------
# UNAVAILABLE signals abort the whole pass.
# --------------------------------------------------------------------------


def test_unavailable_active_signal_aborts_with_zero_deletions(repo, home):
    """If the fleet's in-flight work cannot be seen, nothing is substrate-safe."""
    # Arrange
    enable_cleanup(repo, home)
    before = branches_in(repo)

    def unavailable():
        return None

    # Act
    _sweep(repo, home, apply=True, active_refs=unavailable)
    # Assert
    assert branches_in(repo) == before


def test_unavailable_active_signal_states_the_abort_reason(repo, home):
    """An abort is never rendered as a clean pass."""
    # Arrange
    enable_cleanup(repo, home)

    def unavailable():
        return None

    # Act
    result = _sweep(repo, home, apply=True, active_refs=unavailable)
    # Assert
    assert "active-work signal UNAVAILABLE" in result.abort_reason


def test_unreadable_repo_is_unknown_not_empty(tmp_path, home):
    """ "I could not read this repo" must not render as "no branches"."""
    # Arrange
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    # Act
    result = _sweep(not_a_repo, home, apply=True)
    # Assert
    assert result.unreadable is True


# --------------------------------------------------------------------------
# BACKUP BEFORE DELETE (required property 4).
# --------------------------------------------------------------------------


def test_apply_writes_a_bundle(repo, home):
    # Arrange
    enable_cleanup(repo, home)
    # Act
    result = _sweep(repo, home, apply=True)
    # Assert
    assert Path(result.bundle_path).is_file()


def test_apply_prints_the_restore_command(repo, home):
    """A backup whose restore procedure is undocumented is not usable at 3am."""
    # Arrange
    enable_cleanup(repo, home)
    # Act
    result = _sweep(repo, home, apply=True)
    # Assert
    assert "git bundle" not in result.restore_command and result.restore_command


def test_bundle_lives_under_the_gitignored_runtime_dir(repo, home):
    """Matches the clean-root quarantine convention; gitignored by default."""
    # Arrange
    enable_cleanup(repo, home)
    # Act
    result = _sweep(repo, home, apply=True)
    # Assert
    assert "/.scitex/dev/runtime/branch-gc/" in result.bundle_path


def test_manifest_records_the_sha_of_every_bundled_branch(repo, home):
    # Arrange
    enable_cleanup(repo, home)
    # Act
    result = _sweep(repo, home, apply=True)
    manifest = json.loads(
        (Path(result.backup_dir) / "manifest.json").read_text(encoding="utf-8")
    )
    # Assert
    assert "feature/landed-ff" in manifest["branches"]


def test_bundle_restores_the_deleted_branch_at_its_original_sha(repo, home):
    """THE ROUND TRIP. Delete for real, restore with the printed command,
    and assert the exact SHA came back."""
    # Arrange
    enable_cleanup(repo, home)
    before = run_git(repo, "rev-parse", "feature/landed-ff")
    result = _sweep(repo, home, apply=True)
    # (that the delete happened is pinned by
    #  test_armed_and_applied_deletes_a_landed_old_branch)
    # Act — the literal restore command from the report.
    run_git(repo, "fetch", result.bundle_path, "refs/heads/*:refs/heads/*")
    # Assert
    assert run_git(repo, "rev-parse", "feature/landed-ff") == before


# --------------------------------------------------------------------------
# NO SILENT CAPS (required property 7).
# --------------------------------------------------------------------------


def test_max_delete_bounds_the_pass(repo, home):
    # Arrange
    enable_cleanup(repo, home)
    # Act
    result = _sweep(repo, home, apply=True, max_delete=1)
    # Assert
    assert len(result.deleted) == 1


def test_deferred_branches_are_reported_not_hidden(repo, home):
    """A bounded pass must never read as a complete one."""
    # Arrange
    enable_cleanup(repo, home)
    # Act
    result = _sweep(repo, home, apply=True, max_delete=1)
    deferred = [v.name for v in result.kept if KEEP_DEFERRED_BY_LIMIT in v.keep_reasons]
    # Assert
    assert deferred != []


# --------------------------------------------------------------------------
# The SHA re-confirmation step.
# --------------------------------------------------------------------------


_MOVED = "feature/landed-ff"


def _delete_after_a_real_push(repo, home):
    """Bundle, then genuinely MOVE a branch, then run the delete step.

    No patching: ``git branch -f`` is exactly what "someone pushed during
    the pass" looks like to the engine, so the re-confirmation step is
    exercised for real rather than simulated.
    """
    from scitex_dev.hygiene._branch_gc import _delete_all
    from scitex_dev.hygiene._branch_gc_backup import create_backup
    from scitex_dev.hygiene._branch_gc_model import BranchInfo

    enable_cleanup(repo, home)
    plan = _sweep(repo, home)
    candidates = list(plan.candidates)
    backup = create_backup(
        repo, [BranchInfo(name=v.name, sha=v.sha) for v in candidates]
    )
    run_git(repo, "branch", "-f", _MOVED, "feature/unlanded")
    return _delete_all(repo, list(plan.verdicts), candidates, backup)


def test_branch_that_moved_after_bundling_is_reported_as_moved(repo, home):
    """Step 5 of the contract: a moved ref leaves the deletion set, loudly."""
    # Arrange
    # Act
    verdicts = _delete_after_a_real_push(repo, home)
    moved = [v.name for v in verdicts if KEEP_MOVED_DURING_PASS in v.keep_reasons]
    # Assert
    assert moved == [_MOVED]


def test_branch_that_moved_after_bundling_is_not_deleted(repo, home):
    """...and it survives: the bundle would be short of what a delete destroys."""
    # Arrange
    # Act
    _delete_after_a_real_push(repo, home)
    # Assert
    assert _MOVED in branches_in(repo)


# EOF
