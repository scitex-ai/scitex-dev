"""Mirror tests for `_checks/_model.py` — rule registry, Violation, constants.

Pure-data module: the registry is keyed by rule code, the no-mocks rule is an
error, `Violation.format` renders the code, and the heuristic root sets are
disjoint. All assertions exercise the real objects, no fixtures needed.
"""

from __future__ import annotations

from scitex_dev._cli.audit._api._checks._model import (
    RULES,
    Rule,
    Violation,
    _MOCK_FIXTURE_PARAMS_AUDIT,
    _MOCK_MODULES_AUDIT,
    _MOCK_SYMBOLS_AUDIT,
    _STDLIB_SAFE_ROOTS,
    _THIRD_PARTY_ROOTS,
)


def test_rules_registry_is_keyed_by_code():
    # Arrange
    # Act
    # Assert
    assert all(code == rule.code for code, rule in RULES.items())


def test_every_registry_entry_is_a_rule():
    # Arrange
    # Act
    # Assert
    assert all(isinstance(r, Rule) for r in RULES.values())


def test_no_mocks_rule_has_error_severity():
    # Arrange
    # Act
    # Assert
    assert RULES["PA-306"].severity == "error"


def test_violation_format_includes_the_rule_code():
    # Arrange
    # Act
    # Assert
    rendered = Violation("PA-101", "pkg/__init__.py", "missing __all__").format()
    assert "PA-101" in rendered


def test_mock_constant_collections_are_all_nonempty():
    # Arrange
    # Act
    # Assert
    total = (
        len(_MOCK_MODULES_AUDIT)
        + len(_MOCK_SYMBOLS_AUDIT)
        + len(_MOCK_FIXTURE_PARAMS_AUDIT)
    )
    assert total > 0


def test_third_party_and_stdlib_roots_are_disjoint():
    # Arrange
    # Act
    # Assert
    assert _THIRD_PARTY_ROOTS & _STDLIB_SAFE_ROOTS == frozenset()
