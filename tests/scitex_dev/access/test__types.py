#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Principals, resources, grants and memberships are validated where they are built."""

from __future__ import annotations

import pytest

from scitex_dev.access import (
    AccessConfigError,
    Grant,
    KindSpec,
    Membership,
    Principal,
    Resource,
)

ROUND_TRIP = ["user:alice", "org:lab", "agent:ywatanabe/scitex-hub", "anonymous"]


@pytest.mark.parametrize("text", ROUND_TRIP)
def test_a_principal_parses_and_prints_back(text):
    # Arrange
    parsed = Principal.parse(text)
    # Act
    printed = str(parsed)
    # Assert
    assert printed == text


INVALID_PRINCIPALS = ["alice", "user:", "agent:bot", "agent:a/b/c", "user:../etc", "robot:x", "anonymous:x"]


@pytest.mark.parametrize("text", INVALID_PRINCIPALS)
def test_a_malformed_principal_is_refused(text):
    # Arrange
    malformed = text
    # Act
    raised = pytest.raises(AccessConfigError)
    # Assert
    with raised:
        Principal.parse(malformed)


def test_an_agent_id_names_its_owner():
    # Arrange
    agent = Principal.parse("agent:ywatanabe/scitex-hub")
    # Act
    owner = agent.agent_owner
    # Assert
    assert owner == Principal.parse("user:ywatanabe")


def test_a_resource_owned_by_an_agent_is_refused():
    # Arrange
    agent = Principal.parse("agent:alice/bot")
    # Act
    raised = pytest.raises(AccessConfigError, match="user or an org")
    # Assert
    with raised:
        Resource(kind="demo.doc", path="/x", owner=agent)


def test_a_resource_path_that_traverses_is_refused():
    # Arrange
    owner = Principal.parse("user:alice")
    # Act
    raised = pytest.raises(AccessConfigError)
    # Assert
    with raised:
        Resource(kind="demo.doc", path="/users/alice/../bob", owner=owner)


def test_a_grant_to_anonymous_is_refused():
    # Arrange
    anonymous = Principal.parse("anonymous")
    # Act
    raised = pytest.raises(AccessConfigError, match="public")
    # Assert
    with raised:
        Grant(anonymous, "read", "demo.doc:/x")


def test_a_grant_with_an_unknown_role_is_refused():
    # Arrange
    bob = Principal.parse("user:bob")
    # Act
    raised = pytest.raises(AccessConfigError, match="unknown role")
    # Assert
    with raised:
        Grant(bob, "owner", "demo.doc:/x")


def test_a_membership_in_a_user_is_refused():
    # Arrange
    bob = Principal.parse("user:bob")
    # Act
    raised = pytest.raises(AccessConfigError, match="not an org")
    # Assert
    with raised:
        Membership(bob, Principal.parse("user:alice"), "read")


def test_a_kind_without_actions_is_refused():
    # Arrange
    kwargs = dict(name="demo.doc", path_prefix="/", actions={})
    # Act
    raised = pytest.raises(AccessConfigError, match="no actions")
    # Assert
    with raised:
        KindSpec(**kwargs)


# EOF
