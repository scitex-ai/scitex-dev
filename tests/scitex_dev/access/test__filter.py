#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``accessible()`` agrees with ``check()``: on the shared world and on random fixtures."""

from __future__ import annotations

import pytest

from scitex_dev.access import AccessUnresolved, Principal, accessible, select
from scitex_dev.access.testing import (
    assert_equivalent,
    find_mismatches,
    random_fixture,
)

from ._world import ALICE_DOC, FIXTURE, GRANTS, KINDS, LAB_DOC, MEMBERSHIPS, PUBLIC_DOC


def _visible_paths(principal: str, action: str) -> list[str]:
    access_filter = accessible(
        Principal.parse(principal), action, "demo.doc",
        grants=GRANTS, memberships=MEMBERSHIPS, kinds=KINDS,
    )
    return [resource.path for resource in select(access_filter, FIXTURE.resources)]


LIST_CASES = [
    ("owner-sees-own-and-public", "user:alice", "view", [ALICE_DOC.path, PUBLIC_DOC.path]),
    ("stranger-sees-only-public", "user:mallory", "view", [PUBLIC_DOC.path]),
    ("anonymous-sees-only-public", "anonymous", "view", [PUBLIC_DOC.path]),
    ("org-member-edits-org-content", "user:carol", "edit", [LAB_DOC.path]),
    ("public-is-not-editable", "user:mallory", "edit", []),
    ("agent-ceiling-drops-share", "agent:bob/helper", "share", []),
    ("staff-gets-no-bypass", "user:staff", "edit", []),
]


@pytest.mark.parametrize(
    "principal, action, expected",
    [case[1:] for case in LIST_CASES],
    ids=[case[0] for case in LIST_CASES],
)
def test_accessible_lists_exactly_the_allowed_resources(principal, action, expected):
    # Arrange
    asked = (principal, action)
    # Act
    paths = _visible_paths(*asked)
    # Assert
    assert paths == expected


def test_the_in_memory_filter_matches_check_on_random_fixtures():
    # Arrange
    seeds = range(60)
    # Act
    outcome = assert_equivalent(seeds=seeds)
    # Assert
    assert outcome is None


def test_the_suite_catches_a_selector_that_ignores_public():
    # Arrange
    def select_without_public(access_filter, fixture):
        return {r.ref for r in fixture.resources if r.kind == access_filter.kind and access_filter.matches_grants(r)}
    # Act
    mismatches = find_mismatches(random_fixture(3), select_without_public)
    # Assert
    assert mismatches != []


def test_the_suite_catches_a_selector_that_ignores_the_agent_ceiling():
    # Arrange
    def select_without_ceiling(access_filter, fixture):
        return {
            r.ref for r in fixture.resources
            if r.kind == access_filter.kind
            and ((access_filter.public and r.is_public) or access_filter.matches_grants(r))
        }
    seeds = range(40)
    # Act
    mismatches = [m for seed in seeds for m in find_mismatches(random_fixture(seed), select_without_ceiling)]
    # Assert
    assert any(m.principal.startswith("agent:") for m in mismatches)


def test_an_agent_filter_carries_its_owners_ceiling():
    # Arrange
    agent = Principal.parse("agent:bob/helper")
    # Act
    access_filter = accessible(agent, "edit", "demo.doc", grants=GRANTS, memberships=MEMBERSHIPS, kinds=KINDS)
    # Assert
    assert access_filter.ceiling.resources == frozenset({ALICE_DOC.ref})


def test_accessible_on_an_unregistered_kind_is_unresolved():
    # Arrange
    principal = Principal.parse("user:alice")
    # Act
    raised = pytest.raises(AccessUnresolved, match="kind-unregistered")
    # Assert
    with raised:
        accessible(principal, "view", "ghost.thing", grants=GRANTS, memberships=MEMBERSHIPS, kinds=KINDS)


def test_the_filter_serialises_for_an_adapter():
    # Arrange
    access_filter = accessible(
        Principal.parse("user:dave"), "edit", "demo.doc", grants=GRANTS, memberships=MEMBERSHIPS, kinds=KINDS
    )
    # Act
    payload = access_filter.to_dict()
    # Assert
    assert payload["parents"] == ["demo.project:/users/alice/p1"]


# EOF
