"""Tests for scitex_dev._icons._png (no mocks — real Pillow, real bytes).

Skipped whole-module if Pillow (the [icons] extra) is not installed —
mirrors the repo's lazy-extra pattern (PS-213 LAZY-EXTRA-PATTERN-OK).
"""

from __future__ import annotations

import io

import pytest

PIL = pytest.importorskip("PIL")

from scitex_dev._icons import generate_png, resolve_color  # noqa: E402


def test_generate_png_is_deterministic_across_calls():
    # Arrange
    name = "scitex-todo"
    first = generate_png(name)
    # Act
    second = generate_png(name)
    # Assert
    assert first == second


def test_generate_png_output_is_a_valid_image():
    # Arrange
    from PIL import Image

    data = generate_png("scitex-dev")
    # Act
    img = Image.open(io.BytesIO(data))
    # Assert
    assert img.format == "PNG"


def test_generate_png_respects_requested_size():
    # Arrange
    from PIL import Image

    size = 128
    data = generate_png("scitex-dev", size=size)
    # Act
    img = Image.open(io.BytesIO(data))
    # Assert
    assert img.size == (size, size)


def test_generate_png_uses_resolved_brand_color_for_background_pixel():
    # Arrange
    from PIL import Image

    name = "cct"
    expected_hex = resolve_color(name)
    expected_rgb = tuple(int(expected_hex[i : i + 2], 16) for i in (1, 3, 5))
    data = generate_png(name, size=64)
    # Act
    img = Image.open(io.BytesIO(data))
    corner_pixel = img.convert("RGB").getpixel((0, 0))
    # Assert
    assert corner_pixel == expected_rgb
