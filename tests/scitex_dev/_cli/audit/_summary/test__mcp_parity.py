#!/usr/bin/env python3
"""Tests for scitex_dev._cli.audit._summary._mcp_parity — §6 parity + exemption.

Covers the per-package `[tool.scitex_dev] mcp_parity_exempt` opt-out and the
pure §6 comparison helper. No mocks: synthetic package trees use `tmp_path`,
and the comparison logic is exercised with real name sets.
"""

from __future__ import annotations

from scitex_dev._cli.audit._summary._mcp_parity import (
    _check_api_parity,
    _parity_violations,
    is_mcp_parity_exempt,
)


def _write_pyproject(repo, body: str) -> None:
    """Write a minimal pyproject.toml with `body` appended."""
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "plot-rich"\nversion = "0.0.0"\n' + body
    )


# A plotting-rich tool surface: 5 orphan tools (>3 threshold), zero Python APIs.
_PLOTTING_TOOLS = {"plot", "scatter", "bar", "hist", "boxplot"}


class TestParityComparisonTrips:
    def test_orphan_tool_surface_without_exemption_trips_section_six(self):
        # Arrange
        py_apis: set[str] = set()
        mcp_normalized = set(_PLOTTING_TOOLS)
        # Act
        violations = _parity_violations("plot-rich", py_apis, mcp_normalized)
        # Assert
        assert any(v.rule == "§6" for v in violations)

    def test_matched_tool_surface_produces_no_section_six_violation(self):
        # Arrange
        py_apis = {"save", "load"}
        mcp_normalized = {"save", "load"}
        # Act
        violations = _parity_violations("scitex-io", py_apis, mcp_normalized)
        # Assert
        assert violations == []


class TestExemptionDetection:
    def test_pyproject_flag_marks_package_exempt(self, tmp_path):
        # Arrange
        _write_pyproject(tmp_path, "\n[tool.scitex_dev]\nmcp_parity_exempt = true\n")
        # Act
        exempt = is_mcp_parity_exempt("plot-rich", repo=tmp_path)
        # Assert
        assert exempt is True

    def test_pyproject_without_flag_is_not_exempt(self, tmp_path):
        # Arrange
        _write_pyproject(tmp_path, '\n[tool.scitex_dev]\ncategory = "library"\n')
        # Act
        exempt = is_mcp_parity_exempt("plot-rich", repo=tmp_path)
        # Assert
        assert exempt is False

    def test_yaml_config_flag_marks_package_exempt(self, tmp_path):
        # Arrange
        _write_pyproject(tmp_path, "")
        cfg_dir = tmp_path / ".scitex" / "dev"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.yaml").write_text("audit:\n  mcp-parity-exempt: true\n")
        # Act
        exempt = is_mcp_parity_exempt("plot-rich", repo=tmp_path)
        # Assert
        assert exempt is True

    def test_missing_repo_root_is_not_exempt(self, tmp_path):
        # Arrange
        nonexistent = tmp_path / "does-not-exist"
        # Act
        exempt = is_mcp_parity_exempt("plot-rich", repo=nonexistent)
        # Assert
        assert exempt is False


class TestCheckApiParityHonorsExemption:
    def test_exempt_package_suppresses_orphan_violation(self, tmp_path):
        # Arrange
        _write_pyproject(tmp_path, "\n[tool.scitex_dev]\nmcp_parity_exempt = true\n")
        out: list = []
        # Act
        _check_api_parity("plot-rich", set(_PLOTTING_TOOLS), out, repo=tmp_path)
        # Assert
        assert out == []
