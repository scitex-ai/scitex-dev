#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Drift tests: the Python reasons and decision kinds must equal ``spec/reasons.yaml``."""

from __future__ import annotations

from scitex_dev.access import (
    SPEC,
    AuditReason,
    DecisionKind,
    Reason,
    load_decision_schema,
    load_reasons_spec,
)
from scitex_dev.ci._exit_codes import ExitCode

#: Published reasons. The set is append-only: this pin fails if one is removed or renamed.
PUBLISHED_REASONS = {
    "owner", "grant", "inherited", "org", "implied", "public",
    "not-visible", "role-too-low", "agent-ceiling", "owner-has-no-role", "token-scope",
    "not-signed-in", "not-entitled",
    "enforcer-unreachable", "identity-unresolved", "kind-unregistered",
}


def _yaml_reasons() -> set[str]:
    return {row["reason"] for row in load_reasons_spec()["reasons"]}


def test_code_reasons_equal_the_yaml_reasons():
    # Arrange
    declared = _yaml_reasons()
    # Act
    exposed = {reason.value for reason in Reason}
    # Assert
    assert exposed == declared


def test_code_decision_kinds_equal_the_yaml_decisions():
    # Arrange
    declared = {row["kind"] for row in load_reasons_spec()["decisions"]}
    # Act
    exposed = {kind.value for kind in DecisionKind}
    # Assert
    assert exposed == declared


def test_code_audit_reasons_equal_the_yaml_audit_reasons():
    # Arrange
    declared = {row["reason"] for row in load_reasons_spec()["audit_reasons"]}
    # Act
    exposed = {reason.value for reason in AuditReason}
    # Assert
    assert exposed == declared


def test_no_published_reason_was_removed():
    # Arrange
    declared = _yaml_reasons()
    # Act
    missing = PUBLISHED_REASONS - declared
    # Assert
    assert missing == set()


def test_every_reason_names_a_declared_decision():
    # Arrange
    decisions = {row["kind"] for row in load_reasons_spec()["decisions"]}
    # Act
    used = {row["decision"] for row in load_reasons_spec()["reasons"]}
    # Assert
    assert used <= decisions


def test_every_decision_exit_code_is_a_ci_exit_code():
    # Arrange
    allowed_codes = {member.value for member in ExitCode}
    # Act
    used = {row["exit_code"] for row in load_reasons_spec()["decisions"]}
    # Assert
    assert used <= allowed_codes


def test_the_yaml_declares_the_implemented_spec():
    # Arrange
    document = load_reasons_spec()
    # Act
    declared = document["spec"]
    # Assert
    assert declared == SPEC


def test_the_schema_reason_enum_equals_the_yaml_reasons():
    # Arrange
    schema = load_decision_schema()
    # Act
    enumerated = set(schema["properties"]["reason"]["enum"])
    # Assert
    assert enumerated == _yaml_reasons()


def test_the_schema_decision_kind_enum_equals_the_yaml_decisions():
    # Arrange
    schema = load_decision_schema()
    # Act
    enumerated = set(schema["properties"]["decision"]["properties"]["kind"]["enum"])
    # Assert
    assert enumerated == {row["kind"] for row in load_reasons_spec()["decisions"]}


def test_drift_is_audit_only_and_never_a_decision_reason():
    # Arrange
    declared = _yaml_reasons()
    # Act
    overlap = {reason.value for reason in AuditReason} & declared
    # Assert
    assert overlap == set()


# EOF
