"""Tests for the move-planning/execution engine (`registry_normalize.normalize`).

Covers the hard safety requirements: dry-run by default, archive-not-
delete, live-pid skip, socket-always-skip. CLI-level coverage of the
same behaviours lives in `tests/scitex_dev/_cli/test__registry_normalize.py`.

No mocks (NM001-003) — real temp dirs + a real (self) PID for the
live-process check. Single assert per test.
"""

from __future__ import annotations

import os
from pathlib import Path

from scitex_dev.registry_normalize.normalize import (
    STATUS_MOVED,
    STATUS_PLANNED,
    STATUS_SKIPPED,
    build_plan,
    execute_plan,
    run_registry_normalize,
)


class TestBuildPlanIsPure:
    def test_build_plan_does_not_touch_disk(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("x\n")
        # Act
        build_plan(pkg_dir)
        # Assert — the file is still at its original loose location.
        assert (pkg_dir / "app.log").is_file()

    def test_build_plan_reports_planned_status(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "pkg2"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("x\n")
        # Act
        plan = build_plan(pkg_dir)
        # Assert
        assert all(m.status == STATUS_PLANNED for m in plan)


class TestExecutePlanMoves:
    def test_execute_plan_moves_log_file_to_logs_dir(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "pkg3"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("payload\n")
        plan = build_plan(pkg_dir)
        # Act
        execute_plan(plan)
        # Assert — archived at the destination, nothing deleted (archive-not-delete).
        assert (pkg_dir / "logs" / "app.log").read_text() == "payload\n"

    def test_execute_plan_removes_source_after_move(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "pkg4"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("payload\n")
        plan = build_plan(pkg_dir)
        # Act
        execute_plan(plan)
        # Assert
        assert not (pkg_dir / "app.log").exists()

    def test_execute_plan_marks_moved_status(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "pkg5"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("x\n")
        plan = build_plan(pkg_dir)
        # Act
        executed = execute_plan(plan)
        # Assert
        assert all(m.status == STATUS_MOVED for m in executed)


class TestExecutePlanDestinationCollision:
    """A pre-existing destination must never be silently overwritten —
    that would be a de facto delete despite the archive-not-delete
    invariant (e.g. a second run against a package that keeps
    regenerating the same loose file)."""

    def test_preexisting_destination_is_not_overwritten(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "pkg8"
        pkg_dir.mkdir()
        (pkg_dir / "logs").mkdir()
        (pkg_dir / "logs" / "app.log").write_text("original\n")
        (pkg_dir / "app.log").write_text("new\n")
        plan = build_plan(pkg_dir)
        # Act
        execute_plan(plan)
        # Assert
        assert (pkg_dir / "logs" / "app.log").read_text() == "original\n"

    def test_preexisting_destination_leaves_source_in_place(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        pkg_dir = tmp_path / "pkg9"
        pkg_dir.mkdir()
        (pkg_dir / "logs").mkdir()
        (pkg_dir / "logs" / "app.log").write_text("original\n")
        (pkg_dir / "app.log").write_text("new\n")
        plan = build_plan(pkg_dir)
        # Act
        execute_plan(plan)
        # Assert — nothing deleted; the new file is still where it was.
        assert (pkg_dir / "app.log").read_text() == "new\n"

    def test_preexisting_destination_is_reported_skipped(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        pkg_dir = tmp_path / "pkg10"
        pkg_dir.mkdir()
        (pkg_dir / "logs").mkdir()
        (pkg_dir / "logs" / "app.log").write_text("original\n")
        (pkg_dir / "app.log").write_text("new\n")
        plan = build_plan(pkg_dir)
        # Act
        executed = execute_plan(plan)
        # Assert
        assert all(m.status == STATUS_SKIPPED for m in executed)


class TestLivePidSkip:
    def test_pid_file_naming_live_process_is_skipped(self, tmp_path: Path) -> None:
        # Arrange — os.getpid() is guaranteed alive for the duration of the test.
        pkg_dir = tmp_path / "pkg6"
        pkg_dir.mkdir()
        (pkg_dir / "board.pid").write_text(str(os.getpid()))
        # Act
        plan = build_plan(pkg_dir)
        # Assert
        assert next(m for m in plan if m.src.endswith("board.pid")).status == (
            STATUS_SKIPPED
        )

    def test_pid_file_naming_dead_process_is_planned(self, tmp_path: Path) -> None:
        # Arrange — PID 999999 is exceedingly unlikely to be alive in test envs.
        pkg_dir = tmp_path / "pkg7"
        pkg_dir.mkdir()
        (pkg_dir / "board.pid").write_text("999999")
        # Act
        plan = build_plan(pkg_dir)
        # Assert
        assert next(m for m in plan if m.src.endswith("board.pid")).status == (
            STATUS_PLANNED
        )

    def test_skipped_pid_file_not_moved_by_execute(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "pkg8"
        pkg_dir.mkdir()
        (pkg_dir / "board.pid").write_text(str(os.getpid()))
        plan = build_plan(pkg_dir)
        # Act
        execute_plan(plan)
        # Assert — file remains at its original loose location, untouched.
        assert (pkg_dir / "board.pid").is_file()


class TestSocketAlwaysSkip:
    def test_socket_file_is_always_skipped(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "pkg9"
        pkg_dir.mkdir()
        (pkg_dir / "svc.sock").write_text("")
        # Act
        plan = build_plan(pkg_dir)
        # Assert
        assert next(m for m in plan if m.src.endswith("svc.sock")).status == (
            STATUS_SKIPPED
        )

    def test_socket_skip_detail_mentions_manual_removal(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "pkg10"
        pkg_dir.mkdir()
        (pkg_dir / "svc.sock").write_text("")
        # Act
        plan = build_plan(pkg_dir)
        # Assert
        assert "remove manually" in next(
            m for m in plan if m.src.endswith("svc.sock")
        ).detail


class TestRunRegistryNormalize:
    def test_dry_run_default_does_not_move_files(self, tmp_path: Path) -> None:
        # Arrange
        (tmp_path / "pkg11" / "app.log").parent.mkdir(parents=True)
        (tmp_path / "pkg11" / "app.log").write_text("x\n")
        # Act
        run_registry_normalize("pkg11", confirm=False, scitex_dir=tmp_path)
        # Assert
        assert (tmp_path / "pkg11" / "app.log").is_file()

    def test_confirm_true_moves_files(self, tmp_path: Path) -> None:
        # Arrange
        (tmp_path / "pkg12" / "app.log").parent.mkdir(parents=True)
        (tmp_path / "pkg12" / "app.log").write_text("x\n")
        # Act
        run_registry_normalize("pkg12", confirm=True, scitex_dir=tmp_path)
        # Assert
        assert (tmp_path / "pkg12" / "logs" / "app.log").is_file()

    def test_missing_pkg_dir_reports_error(self, tmp_path: Path) -> None:
        # Arrange
        # (no pkg13 dir created)
        # Act
        report = run_registry_normalize("pkg13", confirm=False, scitex_dir=tmp_path)
        # Assert
        assert report.error is not None
