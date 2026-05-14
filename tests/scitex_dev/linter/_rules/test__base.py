"""Smoke tests for `scitex_dev.linter._rules._base`.

The `Rule` dataclass is exercised by every rule definition; this file
acts as the canonical PS-204/PS-205-mirror for the private module so the
test tree shape matches the src tree shape.
"""

from scitex_dev.linter._rules._base import Rule


def test_rule_is_constructible_rule_id_stx_x001():
    # Arrange
    # Act
    # Assert
    rule = Rule(
        id="STX-X001",
        severity="warning",
        category="test",
        message="m",
        suggestion="s",
    )
    assert rule.id == "STX-X001"


def test_rule_is_constructible_rule_requires():
    # Arrange
    # Act
    # Assert
    rule = Rule(
        id="STX-X001",
        severity="warning",
        category="test",
        message="m",
        suggestion="s",
    )
    assert rule.requires == ""


def test_rule_is_a_dataclass_instance():
    """Rule instances must be hashable so they can be deduplicated by id."""
    # Arrange
    import dataclasses

    rule = Rule(
        id="STX-X002",
        severity="info",
        category="test",
        message="m",
        suggestion="s",
    )
    # Act
    is_dc = dataclasses.is_dataclass(rule)
    # Assert
    assert is_dc


def test_rule_dataclass_is_frozen_against_mutation():
    """frozen=True → assignment raises FrozenInstanceError"""
    # Arrange
    import dataclasses

    import pytest

    rule = Rule(
        id="STX-X002",
        severity="info",
        category="test",
        message="m",
        suggestion="s",
    )
    # Act
    mutate = lambda: setattr(rule, "id", "X")
    # Assert
    with pytest.raises(dataclasses.FrozenInstanceError):
        mutate()
