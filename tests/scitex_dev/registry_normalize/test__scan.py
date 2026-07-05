"""Tests for the pure drift-detection engine (`registry_normalize.scan`).

Shared by the PS-181 audit rule and `scitex-dev registry-normalize` — see
`_cli/audit/_project/test__check_registry_layout.py` for the audit-facing
fixture suite. These tests exercise `scan_pkg_dir`/`scan_registry`
directly, including the `dest` field the normalize CLI plans moves from.

No mocks (NM001-003) — real temp dirs. Single assert per test.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev.registry_normalize.scan import scan_pkg_dir, scan_registry


class TestScanPkgDirDest:
    def test_loose_log_dest_points_under_logs(self, tmp_path: Path) -> None:
        # Arrange
        (tmp_path / "app.log").write_text("x\n")
        # Act
        items = scan_pkg_dir(tmp_path)
        # Assert
        assert next(i.dest for i in items if i.kind == "loose-log") == "logs/app.log"

    def test_archive_dir_dest_strips_underscore_prefix(self, tmp_path: Path) -> None:
        # Arrange
        (tmp_path / "_archive-20260101").mkdir()
        # Act
        items = scan_pkg_dir(tmp_path)
        # Assert
        assert (
            next(i.dest for i in items if i.kind == "archive-dir-naming")
            == "archive/20260101"
        )

    def test_bak_file_dest_includes_date_subdir(self, tmp_path: Path) -> None:
        # Arrange
        (tmp_path / "x.yaml.bak-20260202").write_text("x\n")
        # Act
        items = scan_pkg_dir(tmp_path)
        # Assert
        assert (
            next(i.dest for i in items if i.kind == "bak-file-naming")
            == "archive/20260202/x.yaml.bak-20260202"
        )

    def test_runtime_state_dest_points_under_runtime(self, tmp_path: Path) -> None:
        # Arrange
        (tmp_path / "svc.sock").write_text("")
        # Act
        items = scan_pkg_dir(tmp_path)
        # Assert
        assert (
            next(i.dest for i in items if i.kind == "loose-runtime-state")
            == "runtime/svc.sock"
        )

    def test_loose_script_dest_points_under_scripts(self, tmp_path: Path) -> None:
        # Arrange
        (tmp_path / "run.sh").write_text("#!/bin/sh\n")
        # Act
        items = scan_pkg_dir(tmp_path)
        # Assert
        assert (
            next(i.dest for i in items if i.kind == "loose-script")
            == "scripts/run.sh"
        )

    def test_config_wrong_name_has_no_dest(self, tmp_path: Path) -> None:
        # Arrange — config-naming drift is report-only (no mechanical move).
        (tmp_path / "dashboard.yaml").write_text("x\n")
        # Act
        items = scan_pkg_dir(tmp_path)
        # Assert
        assert next(i for i in items if i.kind == "config-wrong-name").dest is None


class TestScanRegistry:
    def test_scan_registry_omits_conformant_packages(self, tmp_path: Path) -> None:
        # Arrange
        conformant = tmp_path / "clean_pkg"
        (conformant / "runtime").mkdir(parents=True)
        drifted = tmp_path / "dirty_pkg"
        (drifted / "x.log").parent.mkdir(parents=True, exist_ok=True)
        (drifted / "x.log").write_text("x\n")
        # Act
        result = scan_registry(tmp_path)
        # Assert
        assert "clean_pkg" not in result

    def test_scan_registry_reports_drifted_package(self, tmp_path: Path) -> None:
        # Arrange
        drifted = tmp_path / "dirty_pkg2"
        drifted.mkdir()
        (drifted / "x.log").write_text("x\n")
        # Act
        result = scan_registry(tmp_path)
        # Assert
        assert "dirty_pkg2" in result

    def test_scan_registry_missing_scitex_dir_returns_empty(self, tmp_path: Path) -> None:
        # Arrange
        missing = tmp_path / "does-not-exist"
        # Act
        result = scan_registry(missing)
        # Assert
        assert result == {}

    def test_scan_registry_skips_hidden_dirs(self, tmp_path: Path) -> None:
        # Arrange
        hidden = tmp_path / ".hidden_pkg"
        hidden.mkdir()
        (hidden / "x.log").write_text("x\n")
        # Act
        result = scan_registry(tmp_path)
        # Assert
        assert ".hidden_pkg" not in result
