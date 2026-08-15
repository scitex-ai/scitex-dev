#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The deleting half: dry-run by default, and never delete what you could not record.

The runners here are REAL callables that record their argv and return a
CompletedProcess — an alternative launcher, which is what the `runner` seam is
for. No mocking library is involved; the same seam ships in `_relay_ssh`.
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

from scitex_dev.branches._apply import apply_plan, archive_line, tag_name
from scitex_dev.branches._sweep import BranchFacts, Decision, Verdict, plan_sweep

TODAY = date(2026, 8, 15)
OLD = date(2026, 8, 1)


def _stale_plan(*names: str):
    return plan_sweep(
        [
            BranchFacts(
                name=n, last_commit=OLD, has_open_pr=False, pr_merged=False
            )
            for n in names
        ],
        today=TODAY,
    )


class _Recorder:
    """A real launcher that records argv and replies from a script."""

    def __init__(self, *, fail_on: tuple[str, ...] = (), sha: str = "abc123") -> None:
        self.calls: list[list[str]] = []
        self._fail_on = fail_on
        self._sha = sha

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        verb = argv[3] if len(argv) > 3 else ""
        if verb in self._fail_on:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="nope")
        if verb == "log":
            return subprocess.CompletedProcess(
                argv, 0, stdout=f"{self._sha}\x00a subject line\n", stderr=""
            )
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def verbs(self) -> list[str]:
        return [c[3] for c in self.calls if len(c) > 3]


def test_dry_run_is_the_default(tmp_path: Path) -> None:
    """§2: a destructive default that must be opted OUT of is a different
    program from one that must be opted IN to, and only one is schedulable."""
    # Arrange
    runner = _Recorder()
    # Act
    report = apply_plan(
        tmp_path, _stale_plan("feat/a"), today=TODAY,
        archive_path=tmp_path / "log.txt", runner=runner,
    )
    # Assert
    assert report.dry_run is True


def test_a_dry_run_deletes_nothing(tmp_path: Path) -> None:
    # Arrange
    runner = _Recorder()
    # Act
    apply_plan(
        tmp_path, _stale_plan("feat/a"), today=TODAY,
        archive_path=tmp_path / "log.txt", runner=runner,
    )
    # Assert
    assert "branch" not in runner.verbs()


def test_a_dry_run_writes_no_archive_file(tmp_path: Path) -> None:
    # Arrange
    archive = tmp_path / "log.txt"
    # Act
    apply_plan(
        tmp_path, _stale_plan("feat/a"), today=TODAY,
        archive_path=archive, runner=_Recorder(),
    )
    # Assert
    assert archive.exists() is False


def test_a_real_run_archives_then_tags_then_deletes(tmp_path: Path) -> None:
    """ORDER IS THE GUARANTEE, so it is asserted as an order."""
    # Arrange
    runner = _Recorder()
    # Act
    apply_plan(
        tmp_path, _stale_plan("feat/a"), today=TODAY,
        archive_path=tmp_path / "log.txt", dry_run=False, runner=runner,
    )
    # Assert
    assert runner.verbs() == ["log", "tag", "branch"]


def test_a_real_run_records_the_branch_before_dropping_it(tmp_path: Path) -> None:
    # Arrange
    archive = tmp_path / "log.txt"
    # Act
    apply_plan(
        tmp_path, _stale_plan("feat/a"), today=TODAY,
        archive_path=archive, dry_run=False, runner=_Recorder(),
    )
    # Assert
    assert "feat/a" in archive.read_text(encoding="utf-8")


def test_a_failed_tag_cancels_the_delete(tmp_path: Path) -> None:
    """THE RULE THIS MODULE EXISTS FOR.

    A surviving branch is an inconvenience. A branch deleted with no tag and no
    log line is the unrecoverable case the archive is supposed to prevent.
    """
    # Arrange
    runner = _Recorder(fail_on=("tag",))
    # Act
    apply_plan(
        tmp_path, _stale_plan("feat/a"), today=TODAY,
        archive_path=tmp_path / "log.txt", dry_run=False, runner=runner,
    )
    # Assert
    assert "branch" not in runner.verbs()


def test_a_failed_tag_is_reported_not_swallowed(tmp_path: Path) -> None:
    # Arrange
    runner = _Recorder(fail_on=("tag",))
    # Act
    report = apply_plan(
        tmp_path, _stale_plan("feat/a"), today=TODAY,
        archive_path=tmp_path / "log.txt", dry_run=False, runner=runner,
    )
    # Assert
    assert "could not create tag" in report.failures[0].detail


def test_an_unreadable_tip_refuses_the_drop(tmp_path: Path) -> None:
    """If the sha cannot be read, the branch cannot be recorded — so it stays."""
    # Arrange
    runner = _Recorder(fail_on=("log",))
    # Act
    report = apply_plan(
        tmp_path, _stale_plan("feat/a"), today=TODAY,
        archive_path=tmp_path / "log.txt", dry_run=False, runner=runner,
    )
    # Assert
    assert report.failures[0].deleted is False


def test_one_unarchivable_branch_does_not_stop_the_others(tmp_path: Path) -> None:
    """Partial failure is normal; a sweep that aborted on the first would let
    one bad branch preserve every other stale one indefinitely."""
    # Arrange
    calls: list[list[str]] = []

    def runner(argv, **kwargs):
        calls.append(list(argv))
        verb, target = argv[3], argv[-1]
        if verb == "log":
            if "feat/bad" in target:
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
            return subprocess.CompletedProcess(argv, 0, stdout="s\x00subj\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    # Act
    report = apply_plan(
        tmp_path, _stale_plan("feat/bad", "feat/good"), today=TODAY,
        archive_path=tmp_path / "log.txt", dry_run=False, runner=runner,
    )
    # Assert
    assert [o.deleted for o in report.outcomes] == [False, True]


def test_only_the_plans_drops_are_touched(tmp_path: Path) -> None:
    """`apply_plan` re-reads the verdicts rather than trusting a filtered list."""
    # Arrange
    plan = plan_sweep(
        [
            BranchFacts("main", OLD, has_open_pr=False, pr_merged=False),
            BranchFacts("feat/keep", OLD, has_open_pr=True, pr_merged=False),
            BranchFacts("feat/go", OLD, has_open_pr=False, pr_merged=False),
        ],
        today=TODAY,
    )
    runner = _Recorder()
    # Act
    report = apply_plan(
        tmp_path, plan, today=TODAY, archive_path=tmp_path / "log.txt",
        dry_run=False, runner=runner,
    )
    # Assert
    assert [o.name for o in report.outcomes] == ["feat/go"]


def test_the_tag_is_namespaced_by_date(tmp_path: Path) -> None:
    """Branch names are RE-CREATED in this fleet (`pr575`, `chore/changelog-*`).

    A flat namespace would make the second sweep's tag collide with the first's
    and fail — which, under archive-before-delete, silently stops all drops.
    """
    # Arrange
    decision = Decision("feat/a", Verdict.DROP_STALE, 14)
    # Act
    tag = tag_name(decision, today=TODAY)
    # Assert
    assert tag == "archive/20260815/feat/a"


def test_the_archive_line_carries_all_four_recovery_fields() -> None:
    """§5 names them: branch, sha, last-commit date, subject."""
    # Arrange
    decision = Decision("feat/a", Verdict.DROP_STALE, 14)
    # Act
    line = archive_line(decision, "deadbeef", "the subject")
    # Assert
    assert all(t in line for t in ("14d", "deadbeef", "feat/a", "the subject"))


def test_a_clean_run_reports_no_failures(tmp_path: Path) -> None:
    """The positive control — without it, a reporter that flagged everything
    would satisfy every failure test above."""
    # Arrange
    runner = _Recorder()
    # Act
    report = apply_plan(
        tmp_path, _stale_plan("feat/a"), today=TODAY,
        archive_path=tmp_path / "log.txt", dry_run=False, runner=runner,
    )
    # Assert
    assert report.failures == ()


def test_an_empty_plan_does_nothing_and_says_so(tmp_path: Path) -> None:
    # Arrange
    runner = _Recorder()
    # Act
    report = apply_plan(
        tmp_path, plan_sweep([], today=TODAY), today=TODAY,
        archive_path=tmp_path / "log.txt", dry_run=False, runner=runner,
    )
    # Assert
    assert (report.outcomes, runner.calls) == ((), [])


# EOF
