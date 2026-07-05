"""Tests for ``scitex-dev registry-normalize`` — the CLI surface.

Covers: dry-run-by-default (no disk mutation without --yes), confirm-
flag-required-to-act, archive-not-delete, live-pid-skip, socket-always-
skip, and --json output shape. Engine-level coverage (pure
scan/build_plan/execute_plan) lives in
``tests/scitex_dev/registry_normalize/``.

No mocks (NM001-003) — real temp dirs via `--scitex-dir`, never the
real `~/.scitex`. Single assert per test.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("click")

from click.testing import CliRunner

from scitex_dev._cli._root import main


def _run(args: list[str]):
    runner = CliRunner()
    return runner.invoke(main, args)


class TestDryRunByDefault:
    def test_no_yes_flag_leaves_file_in_place(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "demo_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("x\n")
        # Act
        _run(["registry-normalize", "demo_pkg", "--scitex-dir", str(tmp_path)])
        # Assert
        assert (pkg_dir / "app.log").is_file()

    def test_no_yes_flag_reports_dry_run_mode(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "demo_pkg2"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("x\n")
        # Act
        result = _run(["registry-normalize", "demo_pkg2", "--scitex-dir", str(tmp_path)])
        # Assert
        assert "DRY-RUN" in result.output


class TestConfirmFlagRequiredToAct:
    def test_yes_flag_moves_the_file(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "demo_pkg3"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("x\n")
        # Act
        _run(
            [
                "registry-normalize",
                "demo_pkg3",
                "--scitex-dir",
                str(tmp_path),
                "--yes",
            ]
        )
        # Assert
        assert (pkg_dir / "logs" / "app.log").is_file()

    def test_yes_flag_reports_applied_mode(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "demo_pkg4"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("x\n")
        # Act
        result = _run(
            [
                "registry-normalize",
                "demo_pkg4",
                "--scitex-dir",
                str(tmp_path),
                "--yes",
            ]
        )
        # Assert
        assert "APPLIED" in result.output


class TestArchiveNotDelete:
    def test_moved_file_content_is_preserved(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "demo_pkg5"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("important payload\n")
        # Act
        _run(
            [
                "registry-normalize",
                "demo_pkg5",
                "--scitex-dir",
                str(tmp_path),
                "--yes",
            ]
        )
        # Assert
        assert (pkg_dir / "logs" / "app.log").read_text() == "important payload\n"


class TestLivePidSkip:
    def test_live_pid_file_not_moved(self, tmp_path: Path) -> None:
        # Arrange — os.getpid() is guaranteed alive for the test's duration.
        pkg_dir = tmp_path / "demo_pkg6"
        pkg_dir.mkdir()
        (pkg_dir / "board.pid").write_text(str(os.getpid()))
        # Act
        _run(
            [
                "registry-normalize",
                "demo_pkg6",
                "--scitex-dir",
                str(tmp_path),
                "--yes",
            ]
        )
        # Assert
        assert (pkg_dir / "board.pid").is_file()

    def test_live_pid_skip_reason_in_output(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "demo_pkg7"
        pkg_dir.mkdir()
        (pkg_dir / "board.pid").write_text(str(os.getpid()))
        # Act
        result = _run(
            [
                "registry-normalize",
                "demo_pkg7",
                "--scitex-dir",
                str(tmp_path),
                "--yes",
            ]
        )
        # Assert
        assert "SKIPPED (live pid" in result.output


class TestSocketAlwaysSkip:
    def test_socket_file_not_moved_even_with_yes(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "demo_pkg8"
        pkg_dir.mkdir()
        (pkg_dir / "svc.sock").write_text("")
        # Act
        _run(
            [
                "registry-normalize",
                "demo_pkg8",
                "--scitex-dir",
                str(tmp_path),
                "--yes",
            ]
        )
        # Assert
        assert (pkg_dir / "svc.sock").is_file()

    def test_socket_skip_reason_in_output(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "demo_pkg9"
        pkg_dir.mkdir()
        (pkg_dir / "svc.sock").write_text("")
        # Act
        result = _run(
            [
                "registry-normalize",
                "demo_pkg9",
                "--scitex-dir",
                str(tmp_path),
                "--yes",
            ]
        )
        # Assert
        assert "SKIPPED (socket" in result.output


class TestJsonOutput:
    def test_json_output_is_valid_json(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "demo_pkg10"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("x\n")
        # Act
        result = _run(
            [
                "registry-normalize",
                "demo_pkg10",
                "--scitex-dir",
                str(tmp_path),
                "--json",
            ]
        )
        # Assert
        payload = json.loads(result.output)
        assert "moves" in payload

    def test_json_output_reports_planned_move(self, tmp_path: Path) -> None:
        # Arrange
        pkg_dir = tmp_path / "demo_pkg11"
        pkg_dir.mkdir()
        (pkg_dir / "app.log").write_text("x\n")
        # Act
        result = _run(
            [
                "registry-normalize",
                "demo_pkg11",
                "--scitex-dir",
                str(tmp_path),
                "--json",
            ]
        )
        # Assert
        payload = json.loads(result.output)
        assert payload["moves"][0]["status"] == "planned"


class TestMissingPackage:
    def test_missing_pkg_dir_exits_nonzero(self, tmp_path: Path) -> None:
        # Arrange
        # (no package dir created under tmp_path)
        # Act
        result = _run(
            ["registry-normalize", "nonexistent_pkg", "--scitex-dir", str(tmp_path)]
        )
        # Assert
        assert result.exit_code != 0
