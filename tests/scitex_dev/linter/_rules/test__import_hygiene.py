"""Tests for the in-house STX-I001-I007 import-hygiene rules.

These rules were absorbed from the scitex-umbrella plugin
(``scitex._linter_plugin``) into the engine registry
(umbrella-thinning Phase A). They must be discoverable straight from
``scitex_dev.linter._rules.ALL_RULES`` — no umbrella plugin required —
and they must stay gated on ``requires="scitex"`` so they fire only when
the scitex umbrella is installed.
"""

import pytest

from scitex_dev.linter._rules import ALL_RULES
from scitex_dev.linter._rules import _import_hygiene as ih

I_RULES = [ih.I001, ih.I002, ih.I003, ih.I004, ih.I005, ih.I006, ih.I007]
I_IDS = [f"STX-I00{i}" for i in range(1, 8)]


@pytest.mark.parametrize("rule_id", I_IDS)
def test_import_rule_is_registered_in_all_rules(rule_id):
    # Arrange
    # Act
    rule = ALL_RULES.get(rule_id)
    # Assert
    assert rule is not None, f"{rule_id} not in engine ALL_RULES"


@pytest.mark.parametrize("rule_id", I_IDS)
def test_import_rule_requires_scitex(rule_id):
    """All STX-I00x rules gate on scitex being installed."""
    # Arrange
    rule = ALL_RULES[rule_id]
    # Act
    # Assert
    assert rule.requires == "scitex"


@pytest.mark.parametrize("rule", I_RULES)
def test_import_rule_category_is_import(rule):
    # Arrange
    # Act
    # Assert
    assert rule.category == "import"


@pytest.mark.parametrize("rule", I_RULES)
def test_import_rule_severity_is_known(rule):
    # Arrange
    # Act
    # Assert
    assert rule.severity in {"error", "warning", "info"}


def test_module_exposes_all_seven_import_rule_ids():
    # Arrange
    # Act
    got = sorted(r.id for r in I_RULES)
    # Assert
    assert got == sorted(I_IDS)


def test_i006_is_info_severity():
    """STX-I006 (random → rngg) is the only info-level import rule."""
    # Arrange
    # Act
    # Assert
    assert ALL_RULES["STX-I006"].severity == "info"
