#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``check()`` rules, table-driven over one hand-built world."""

from __future__ import annotations

import pytest

from scitex_dev.access import (
    AccessConfigError,
    AccessDenied,
    AccessUnresolved,
    DecisionKind,
    Principal,
    Reason,
    Resource,
    check,
    decide_missing,
    require,
)

from ._world import ALICE_DOC, GHOST, GRANTS, KINDS, LAB_DOC, MEMBERSHIPS, PUBLIC_DOC


def _decide(principal: str, action: str, resource: Resource):
    return check(
        Principal.parse(principal),
        action,
        resource,
        grants=GRANTS,
        memberships=MEMBERSHIPS,
        kinds=KINDS,
    )


REASON_CASES = [
    ("owner-is-admin", "user:alice", "share", ALICE_DOC, Reason.OWNER),
    ("explicit-grant", "user:bob", "edit", ALICE_DOC, Reason.GRANT),
    ("inherited-default-grant", "user:dave", "edit", ALICE_DOC, Reason.INHERITED),
    ("org-owner-via-membership", "user:carol", "edit", LAB_DOC, Reason.ORG),
    ("org-grant-capped-by-membership", "user:rita", "view", ALICE_DOC, Reason.ORG),
    ("public-signed-in", "user:mallory", "view", PUBLIC_DOC, Reason.PUBLIC),
    ("public-anonymous", "anonymous", "view", PUBLIC_DOC, Reason.PUBLIC),
    ("private-no-role-not-visible", "user:mallory", "view", ALICE_DOC, Reason.NOT_VISIBLE),
    ("read-grant-cannot-edit", "user:frank", "edit", ALICE_DOC, Reason.ROLE_TOO_LOW),
    ("membership-caps-org-owner", "user:carol", "share", LAB_DOC, Reason.ROLE_TOO_LOW),
    ("membership-caps-org-grant", "user:rita", "edit", ALICE_DOC, Reason.ROLE_TOO_LOW),
    ("public-gives-only-read", "user:mallory", "edit", PUBLIC_DOC, Reason.ROLE_TOO_LOW),
    ("anonymous-private", "anonymous", "view", ALICE_DOC, Reason.NOT_SIGNED_IN),
    ("anonymous-write-public", "anonymous", "edit", PUBLIC_DOC, Reason.NOT_SIGNED_IN),
    ("agent-delegated-under-owner", "agent:alice/bot", "edit", ALICE_DOC, Reason.GRANT),
    ("agent-grant-is-its-limit", "agent:alice/bot", "share", ALICE_DOC, Reason.ROLE_TOO_LOW),
    ("agent-capped-to-owner-role", "agent:bob/helper", "edit", ALICE_DOC, Reason.GRANT),
    ("agent-ceiling", "agent:bob/helper", "share", ALICE_DOC, Reason.AGENT_CEILING),
    ("agent-owner-has-no-role", "agent:erin/bot", "edit", ALICE_DOC, Reason.OWNER_HAS_NO_ROLE),
    ("agent-no-implicit-delegation", "agent:alice/other", "view", ALICE_DOC, Reason.NOT_VISIBLE),
    ("agent-reads-public", "agent:erin/bot", "view", PUBLIC_DOC, Reason.PUBLIC),
    ("no-staff-bypass", "user:staff", "view", ALICE_DOC, Reason.NOT_VISIBLE),
    ("kind-unregistered", "user:alice", "view", GHOST, Reason.KIND_UNREGISTERED),
]


@pytest.mark.parametrize(
    "principal, action, resource, expected",
    [case[1:] for case in REASON_CASES],
    ids=[case[0] for case in REASON_CASES],
)
def test_check_gives_the_expected_reason(principal, action, resource, expected):
    # Arrange
    asked = (principal, action, resource)
    # Act
    decision = _decide(*asked)
    # Assert
    assert decision.reason is expected


KIND_CASES = [
    ("allowed", "user:alice", "view", ALICE_DOC, DecisionKind.ALLOWED),
    ("denied", "user:mallory", "view", ALICE_DOC, DecisionKind.DENIED),
    ("not-signed-in", "anonymous", "view", ALICE_DOC, DecisionKind.NOT_SIGNED_IN),
    ("unresolved", "user:alice", "view", GHOST, DecisionKind.UNRESOLVED),
]


@pytest.mark.parametrize(
    "principal, action, resource, expected",
    [case[1:] for case in KIND_CASES],
    ids=[case[0] for case in KIND_CASES],
)
def test_check_gives_the_expected_decision_kind(principal, action, resource, expected):
    # Arrange
    asked = (principal, action, resource)
    # Act
    decision = _decide(*asked)
    # Assert
    assert decision.kind is expected


def test_the_held_role_of_a_capped_agent_is_its_owners_role():
    # Arrange
    asked = ("agent:bob/helper", "share", ALICE_DOC)
    # Act
    decision = _decide(*asked)
    # Assert
    assert decision.role == "write"


def test_a_missing_resource_renders_identically_to_a_private_one():
    # Arrange
    private = _decide("user:mallory", "view", ALICE_DOC).to_dict()
    # Act
    missing = decide_missing(
        Principal.parse("user:mallory"), "view", ALICE_DOC.ref, kinds=KINDS
    ).to_dict()
    # Assert
    assert {**missing, "exchange_id": None} == {**private, "exchange_id": None}


def test_a_missing_resource_asked_anonymously_is_not_signed_in():
    # Arrange
    ref = "demo.doc:/users/nobody/none"
    # Act
    decision = decide_missing(Principal.parse("anonymous"), "view", ref, kinds=KINDS)
    # Assert
    assert decision.reason is Reason.NOT_SIGNED_IN


def test_require_raises_access_denied_for_a_denial():
    # Arrange
    principal = Principal.parse("user:mallory")
    # Act
    raised = pytest.raises(AccessDenied)
    # Assert
    with raised:
        require(principal, "view", ALICE_DOC, grants=GRANTS, memberships=MEMBERSHIPS, kinds=KINDS)


def test_require_raises_access_unresolved_for_an_unregistered_kind():
    # Arrange
    principal = Principal.parse("user:alice")
    # Act
    raised = pytest.raises(AccessUnresolved)
    # Assert
    with raised:
        require(principal, "view", GHOST, grants=GRANTS, memberships=MEMBERSHIPS, kinds=KINDS)


def test_access_denied_is_a_permission_error():
    # Arrange
    principal = Principal.parse("user:mallory")
    # Act
    raised = pytest.raises(PermissionError)
    # Assert
    with raised:
        require(principal, "view", ALICE_DOC, grants=GRANTS, memberships=MEMBERSHIPS, kinds=KINDS)


def test_require_returns_the_decision_when_allowed():
    # Arrange
    principal = Principal.parse("user:alice")
    # Act
    decision = require(principal, "view", ALICE_DOC, grants=GRANTS, memberships=MEMBERSHIPS, kinds=KINDS)
    # Assert
    assert decision.reason is Reason.OWNER


def test_an_undeclared_action_is_a_config_error():
    # Arrange
    asked = ("user:alice", "delete-everything", ALICE_DOC)
    # Act
    raised = pytest.raises(AccessConfigError, match="has no action")
    # Assert
    with raised:
        _decide(*asked)


# EOF
