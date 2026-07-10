"""Tests for scitex_dev._icons._label (no mocks — pure functions)."""

from __future__ import annotations

from scitex_dev._icons import derive_label


def test_single_word_uses_first_max_chars_uppercased():
    # Arrange
    name = "figrecipe"
    # Act
    label = derive_label(name, max_chars=3)
    # Assert
    assert label == "FIG"


def test_multi_word_uses_first_letter_of_each_word():
    # Arrange
    name = "claude-code-telegrammer"
    # Act
    label = derive_label(name, max_chars=3)
    # Assert
    assert label == "CCT"


def test_label_is_deterministic_across_calls():
    # Arrange
    name = "scitex-todo"
    first = derive_label(name)
    # Act
    second = derive_label(name)
    # Assert
    assert first == second


def test_empty_name_returns_placeholder():
    # Arrange
    name = "   "
    # Act
    label = derive_label(name)
    # Assert
    assert label == "?"


def test_max_chars_limits_multi_word_label_length():
    # Arrange
    name = "a-b-c-d-e-f"
    # Act
    label = derive_label(name, max_chars=2)
    # Assert
    assert label == "AB"
