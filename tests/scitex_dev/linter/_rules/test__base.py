"""Smoke tests for `scitex_dev.linter._rules._base`.

The `Rule` dataclass is exercised by every rule definition; this file
acts as the canonical PS-204/PS-205-mirror for the private module so the
test tree shape matches the src tree shape.
"""

from scitex_dev.linter._rules._base import Rule


def test_rule_is_constructible():
    rule = Rule(
        id="STX-X001",
        severity="warning",
        category="test",
        message="m",
        suggestion="s",
    )
    assert rule.id == "STX-X001"
    assert rule.requires == ""


def test_rule_is_frozen():
    """Rule instances must be hashable so they can be deduplicated by id."""
    import dataclasses

    rule = Rule(
        id="STX-X002",
        severity="info",
        category="test",
        message="m",
        suggestion="s",
    )
    assert dataclasses.is_dataclass(rule)
    # frozen=True → assignment raises FrozenInstanceError
    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        rule.id = "X"
