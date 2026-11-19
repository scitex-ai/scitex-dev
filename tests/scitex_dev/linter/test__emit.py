"""spi.add_issue — the one emission gate shared by engine and plugins."""

from __future__ import annotations

from scitex_dev.linter._emit import add_issue
from scitex_dev.linter.config import LinterConfig
from scitex_dev.linter.spi import Rule

RULE = Rule("TEST-E1", "warning", "io", "Test message", "Fix it.", requires="pkg")
FREE = Rule("TEST-E2", "warning", "io", "Test message", "Fix it.")
AVAILABLE = {"pkg": True}


def _emit(rule=RULE, source_line="x = 1", config=None, available=AVAILABLE):
    issues = []
    add_issue(
        issues, rule, 3, 4, source_line, config or LinterConfig(), available=available
    )
    return issues


def test_add_issue_appends_finding_at_line_and_col():
    # Arrange
    # Act
    issues = _emit()
    # Assert
    assert [(i.rule.id, i.line, i.col) for i in issues] == [("TEST-E1", 3, 4)]


def test_add_issue_drops_rule_whose_requirement_is_missing():
    # Arrange
    available = {"pkg": False}
    # Act
    issues = _emit(available=available)
    # Assert
    assert issues == []


def test_add_issue_ignores_none_rule_for_lean_envs():
    # Arrange
    # Act
    issues = _emit(rule=None)
    # Assert
    assert issues == []


def test_add_issue_respects_config_disable():
    # Arrange
    config = LinterConfig(disable=["TEST-E1"])
    # Act
    issues = _emit(config=config)
    # Assert
    assert issues == []


def test_add_issue_respects_stx_allow_comment():
    # Arrange
    source_line = "x = 1  # stx-allow: TEST-E1"
    # Act
    issues = _emit(source_line=source_line)
    # Assert
    assert issues == []


def test_per_rule_pin_wins_over_category_floor():
    # Arrange
    config = LinterConfig(
        per_rule_severity={"TEST-E2": "info"},
        category_severity_override={"io": "error"},
    )
    # Act
    issues = _emit(rule=FREE, config=config)
    # Assert
    assert issues[0].rule.severity == "info"


def test_category_floor_applies_without_per_rule_pin():
    # Arrange
    config = LinterConfig(category_severity_override={"io": "error"})
    # Act
    issues = _emit(rule=FREE, config=config)
    # Assert
    assert issues[0].rule.severity == "error"
