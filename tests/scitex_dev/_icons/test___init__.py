"""Tests for scitex_dev._icons.save_icon (no mocks — real filesystem via tmp_path)."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from scitex_dev._icons import save_icon  # noqa: E402


def test_save_icon_writes_svg_file(tmp_path):
    # Arrange
    name = "scitex-todo"
    # Act
    written = save_icon(name, tmp_path, formats=("svg",))
    # Assert
    assert written["svg"].is_file()


def test_save_icon_writes_png_file(tmp_path):
    # Arrange
    name = "scitex-todo"
    # Act
    written = save_icon(name, tmp_path, formats=("png",))
    # Assert
    assert written["png"].is_file()


def test_save_icon_svg_content_matches_generate_svg(tmp_path):
    # Arrange
    from scitex_dev._icons import generate_svg

    name = "scitex-dev"
    expected = generate_svg(name)
    # Act
    written = save_icon(name, tmp_path, formats=("svg",))
    # Assert
    assert written["svg"].read_text() == expected


def test_save_icon_derives_slug_from_name_for_filename(tmp_path):
    # Arrange
    name = "My Cool Agent!"
    # Act
    written = save_icon(name, tmp_path, formats=("svg",))
    # Assert
    assert written["svg"].name == "my-cool-agent.svg"


def test_save_icon_honours_explicit_stem_override(tmp_path):
    # Arrange
    # Act
    written = save_icon("scitex-dev", tmp_path, formats=("svg",), stem="custom")
    # Assert
    assert written["svg"].name == "custom.svg"


def test_save_icon_creates_missing_output_directory(tmp_path):
    # Arrange
    nested = tmp_path / "a" / "b" / "c"
    # Act
    save_icon("scitex-dev", nested, formats=("svg",))
    # Assert
    assert nested.is_dir()
