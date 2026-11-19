"""Retired rule ids are reserved, inactive, and warn when still configured."""

from __future__ import annotations

import warnings

from scitex_dev.linter._rules import ALL_RULES
from scitex_dev.linter._rules._retired import RETIRED, warn_retired_config
from scitex_dev.linter.config import LinterConfig


def test_retired_ids_are_absent_from_active_rules():
    # Arrange
    retired = set(RETIRED)
    # Act
    active = retired & set(ALL_RULES)
    # Assert
    assert active == set()


def test_retired_rule_objects_stay_importable_for_back_compat():
    # Arrange
    from scitex_dev.linter.rules import I004

    # Act
    rule_id = I004.id
    # Assert
    assert rule_id == "STX-I004"


def test_config_naming_a_retired_id_warns_with_its_successor():
    # Arrange
    config = LinterConfig(disable=["STX-I005"])
    # Act
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warn_retired_config(config)
    # Assert
    assert "STX-IO001" in str(caught[0].message)


def test_config_without_retired_ids_is_silent():
    # Arrange
    config = LinterConfig(disable=["STX-I001"])
    # Act
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warn_retired_config(config)
    # Assert
    assert caught == []
