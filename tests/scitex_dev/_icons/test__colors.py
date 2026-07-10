"""Tests for scitex_dev._icons._colors (no mocks — pure functions)."""

from __future__ import annotations

import re

from scitex_dev._icons import KNOWN_COLORS, resolve_color

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_known_name_returns_curated_color():
    # Arrange
    # (cct is a curated entry in KNOWN_COLORS)
    # Act
    color = resolve_color("cct")
    # Assert
    assert color == KNOWN_COLORS["cct"]


def test_known_name_lookup_is_whitespace_insensitive():
    # Arrange
    padded = "  cct  "
    # Act
    color = resolve_color(padded)
    # Assert
    assert color == KNOWN_COLORS["cct"]


def test_known_name_lookup_is_case_insensitive():
    # Arrange
    mixed_case = "Writer"
    # Act
    color = resolve_color(mixed_case)
    # Assert
    assert color == KNOWN_COLORS["writer"]


def test_unmapped_name_falls_back_to_valid_hex_color():
    # Arrange
    name = "some-totally-unregistered-package-xyz"
    # Act
    color = resolve_color(name)
    # Assert
    assert _HEX_RE.match(color)


def test_unmapped_name_fallback_is_deterministic_across_calls():
    # Arrange
    name = "another-unregistered-name"
    first = resolve_color(name)
    # Act
    second = resolve_color(name)
    # Assert
    assert first == second


def test_different_unmapped_names_can_get_different_colors():
    # Arrange
    names = [f"pkg-{i}" for i in range(20)]
    # Act
    colors = {resolve_color(n) for n in names}
    # Assert: the fallback palette has >1 entry, so 20 distinct names
    # should not all collapse onto a single color.
    assert len(colors) > 1


def test_all_known_colors_are_valid_hex():
    # Arrange
    colors = list(KNOWN_COLORS.values())
    # Act
    all_valid = all(_HEX_RE.match(c) for c in colors)
    # Assert
    assert all_valid
