"""Tests for the engine rule registry assembled in `_rules/__init__.py`.

Focus: the umbrella-thinning Phase A contract. The scitex-umbrella's
``scitex._linter_plugin`` formerly *supplied* the 15 STX-I001-I007 +
STX-S001-S008 rules via the ``scitex_dev.linter.plugins`` entry point.
After Phase A the engine owns them outright in ``ALL_RULES``. These
tests pin that every id resolves from the engine's OWN registry (no
plugin needed) so the umbrella can delete its ``_linter_plugin.py``
without losing any rule, and that the scitex-gated rules keep
``requires="scitex"`` for identical runtime behavior.
"""

import pytest

from scitex_dev.linter._rules import ALL_RULES, lookup, reset_lookup_cache

ABSORBED_IDS = [f"STX-I00{i}" for i in range(1, 8)] + [
    f"STX-S00{i}" for i in range(1, 9)
]

# requires gating preserved verbatim from the former umbrella plugin.
SCITEX_GATED = {
    "STX-I001",
    "STX-I002",
    "STX-I003",
    "STX-I004",
    "STX-I005",
    "STX-I006",
    "STX-I007",
    "STX-S001",
    "STX-S003",
    "STX-S004",
    "STX-S005",
    "STX-S006",
}


def test_all_fifteen_absorbed_ids_in_engine_registry():
    """All 15 ids live in the engine's ALL_RULES dict — no plugin needed."""
    # Arrange
    # Act
    missing = [rid for rid in ABSORBED_IDS if rid not in ALL_RULES]
    # Assert
    assert not missing, f"missing from engine registry: {missing}"


@pytest.mark.parametrize("rule_id", sorted(SCITEX_GATED))
def test_absorbed_rule_still_requires_scitex(rule_id):
    """Gated rules keep identical runtime behavior (fire only w/ scitex)."""
    # Arrange
    rule = ALL_RULES[rule_id]
    # Act
    # Assert
    assert rule.requires == "scitex"


def test_absorbed_ids_are_engine_owned_not_plugin_sourced():
    """The 15 ids come from the engine's OWN registry, not a plugin.

    Simulates the umbrella having deleted its `_linter_plugin.py`: the
    engine builds `ALL_RULES` purely from its own `_rules/*.py` modules
    (no entry-point discovery runs to populate that dict). If every id is
    present there, dropping the umbrella plugin loses no rule.
    """
    # Arrange — ALL_RULES is assembled in `_rules/__init__.py` with zero
    # plugin involvement; importing it does not trigger plugin discovery.
    # Act
    engine_rules = {rid: ALL_RULES.get(rid) for rid in ABSORBED_IDS}
    # Assert
    plugin_sourced = [rid for rid, r in engine_rules.items() if r is None]
    assert not plugin_sourced, f"still plugin-sourced (not in-house): {plugin_sourced}"


def test_lookup_resolves_all_absorbed_ids():
    """End-to-end: `lookup()` (engine + plugin merge) resolves all 15."""
    # Arrange
    reset_lookup_cache()
    try:
        # Act
        unresolved = [rid for rid in ABSORBED_IDS if lookup(rid) is None]
        # Assert
        assert not unresolved, f"lookup() could not resolve: {unresolved}"
    finally:
        reset_lookup_cache()


def test_no_id_drift_exactly_fifteen_absorbed():
    """Guard against a typo silently dropping a rule id."""
    # Arrange
    # Act
    present = [rid for rid in ABSORBED_IDS if rid in ALL_RULES]
    # Assert
    assert len(present) == 15
