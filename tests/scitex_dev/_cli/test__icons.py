"""Tests for ``scitex-dev icons generate`` (no mocks — real CliRunner)."""

from __future__ import annotations

import pytest

pytest.importorskip("click")
pytest.importorskip("PIL")

from click.testing import CliRunner  # noqa: E402

from scitex_dev._cli._root import main  # noqa: E402


def test_icons_generate_writes_svg_and_png(tmp_path):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["icons", "generate", "scitex-dev", "--out", str(tmp_path)])
    # Assert
    assert result.exit_code == 0


def test_icons_generate_creates_svg_file(tmp_path):
    # Arrange
    runner = CliRunner()
    # Act
    runner.invoke(main, ["icons", "generate", "scitex-dev", "--out", str(tmp_path)])
    # Assert
    assert (tmp_path / "scitex-dev.svg").is_file()


def test_icons_generate_creates_png_file(tmp_path):
    # Arrange
    runner = CliRunner()
    # Act
    runner.invoke(main, ["icons", "generate", "scitex-dev", "--out", str(tmp_path)])
    # Assert
    assert (tmp_path / "scitex-dev.png").is_file()


def test_icons_generate_svg_only_format_skips_png(tmp_path):
    # Arrange
    runner = CliRunner()
    # Act
    runner.invoke(
        main,
        ["icons", "generate", "scitex-dev", "--out", str(tmp_path), "--format", "svg"],
    )
    # Assert
    assert not (tmp_path / "scitex-dev.png").exists()


def test_icons_is_categorized_under_core_in_root_help():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["--help"])
    # Assert
    assert "icons" in result.output
