#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kind registration: aggregation, conflicts, and fail-closed on a broken provider."""

from __future__ import annotations

import pytest

from scitex_dev.access import AccessConfigError, KindSpec, discover_kinds

_ACTIONS = {"view": "read"}


def provide_cards():
    return [KindSpec(name="cards.card", path_prefix="/users/", actions=_ACTIONS)]


def provide_other_cards():
    return [KindSpec(name="cards.card", path_prefix="/orgs/", actions=_ACTIONS)]


def provide_nothing_but_errors():
    raise ImportError("scitex_cards is half-installed")


def test_discovery_aggregates_provided_kinds():
    # Arrange
    providers = [provide_cards]
    # Act
    registry = discover_kinds(extra_providers=providers, include_entry_points=False)
    # Assert
    assert list(registry) == ["cards.card"]


def test_discovery_stamps_the_provider_as_the_package():
    # Arrange
    providers = [provide_cards]
    # Act
    registry = discover_kinds(extra_providers=providers, include_entry_points=False)
    # Assert
    assert registry["cards.card"].package == "provide_cards"


def test_one_kind_registered_twice_with_different_rules_is_refused():
    # Arrange
    providers = [provide_cards, provide_other_cards]
    # Act
    raised = pytest.raises(AccessConfigError, match="registered twice")
    # Assert
    with raised:
        discover_kinds(extra_providers=providers, include_entry_points=False)


def test_a_broken_provider_warns_and_leaves_its_kinds_unregistered():
    # Arrange
    providers = [provide_nothing_but_errors]
    # Act
    warned = pytest.warns(RuntimeWarning, match="unregistered")
    # Assert
    with warned:
        discover_kinds(extra_providers=providers, include_entry_points=False)


def test_a_kind_spec_reports_the_role_an_action_needs():
    # Arrange
    spec = provide_cards()[0]
    # Act
    role = spec.required_role("view")
    # Assert
    assert role == "read"


# EOF
