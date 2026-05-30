"""Tests for the in-house STX-S001-S008 structure rules.

Absorbed from the scitex-umbrella plugin (``scitex._linter_plugin``)
into the engine registry (umbrella-thinning Phase A). They must be
discoverable straight from ``scitex_dev.linter._rules.ALL_RULES``.

The ``requires`` gate is intentionally NOT uniform — verbatim from the
former umbrella plugin: S001/S003/S004/S005/S006 reference
``@stx.session`` / ``import scitex`` and gate on ``requires="scitex"``,
while S002/S007/S008 are generic structure/naming checks with no gate.
"""

import pytest

from scitex_dev.linter._rules import ALL_RULES
from scitex_dev.linter._rules import _session_structure as ss

S_RULES = [
    ss.S001,
    ss.S002,
    ss.S003,
    ss.S004,
    ss.S005,
    ss.S006,
    ss.S007,
    ss.S008,
]
S_IDS = [f"STX-S00{i}" for i in range(1, 9)]

# Verbatim gating preserved from the former umbrella plugin.
SCITEX_GATED = {"STX-S001", "STX-S003", "STX-S004", "STX-S005", "STX-S006"}
UNGATED = {"STX-S002", "STX-S007", "STX-S008"}


@pytest.mark.parametrize("rule_id", S_IDS)
def test_structure_rule_is_registered_in_all_rules(rule_id):
    # Arrange
    # Act
    rule = ALL_RULES.get(rule_id)
    # Assert
    assert rule is not None, f"{rule_id} not in engine ALL_RULES"


@pytest.mark.parametrize("rule_id", sorted(SCITEX_GATED))
def test_scitex_gated_structure_rule_requires_scitex(rule_id):
    # Arrange
    rule = ALL_RULES[rule_id]
    # Act
    # Assert
    assert rule.requires == "scitex"


@pytest.mark.parametrize("rule_id", sorted(UNGATED))
def test_generic_structure_rule_is_ungated(rule_id):
    """S002/S007/S008 fire regardless of scitex install — verbatim behavior."""
    # Arrange
    rule = ALL_RULES[rule_id]
    # Act
    # Assert
    assert rule.requires == ""


@pytest.mark.parametrize("rule", S_RULES)
def test_structure_rule_category_is_structure(rule):
    # Arrange
    # Act
    # Assert
    assert rule.category == "structure"


def test_module_exposes_all_eight_structure_rule_ids():
    # Arrange
    # Act
    got = sorted(r.id for r in S_RULES)
    # Assert
    assert got == sorted(S_IDS)


def test_s001_is_error_severity():
    # Arrange
    # Act
    # Assert
    assert ALL_RULES["STX-S001"].severity == "error"
