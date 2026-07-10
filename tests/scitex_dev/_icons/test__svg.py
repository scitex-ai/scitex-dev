"""Tests for scitex_dev._icons._svg (no mocks — pure functions)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from scitex_dev._icons import generate_svg, resolve_color


def test_generate_svg_is_deterministic_across_calls():
    # Arrange
    name = "scitex-todo"
    first = generate_svg(name)
    # Act
    second = generate_svg(name)
    # Assert
    assert first == second


def test_generate_svg_output_is_valid_xml():
    # Arrange
    svg = generate_svg("scitex-dev")
    # Act
    root = ET.fromstring(svg)
    # Assert
    assert root.tag.endswith("svg")


def test_generate_svg_uses_resolved_brand_color_as_fill():
    # Arrange
    name = "cct"
    expected_color = resolve_color(name)
    # Act
    svg = generate_svg(name)
    # Assert
    assert f'fill="{expected_color}"' in svg


def test_generate_svg_honours_explicit_color_override():
    # Arrange
    override = "#123456"
    # Act
    svg = generate_svg("cct", color=override)
    # Assert
    assert f'fill="{override}"' in svg


def test_generate_svg_omits_wordmark_when_none():
    # Arrange
    with_wordmark = generate_svg("scitex-dev", wordmark="SciTeX")
    # Act
    without_wordmark = generate_svg("scitex-dev", wordmark=None)
    # Assert
    assert without_wordmark.count("<text") < with_wordmark.count("<text")


def test_generate_svg_escapes_special_characters_in_label():
    # Arrange
    unsafe_label = "<A&B>"
    # Act
    svg = generate_svg("a&b", label=unsafe_label)
    # Assert
    assert "&amp;" in svg


def test_generate_svg_respects_requested_size():
    # Arrange
    size = 256
    # Act
    svg = generate_svg("scitex-dev", size=size)
    # Assert
    assert f'width="{size}"' in svg
