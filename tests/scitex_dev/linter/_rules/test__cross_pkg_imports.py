"""Smoke tests for the STX-I008 rule definition."""

from scitex_dev.linter._rules import ALL_RULES
from scitex_dev.linter._rules._cross_pkg_imports import I008


def test_i008_has_expected_id():
    # Arrange
    # Act
    # Assert
    assert I008.id == "STX-I008"


def test_i008_severity_is_warning():
    # Arrange
    # Act
    # Assert
    assert I008.severity == "warning"


def test_i008_category_is_import():
    # Arrange
    # Act
    # Assert
    assert I008.category == "import"


def test_i008_is_registered_in_all_rules():
    # Arrange
    # Act
    rule = ALL_RULES.get("STX-I008")
    # Assert
    assert rule is I008
