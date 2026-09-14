#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The AccessDecision envelope: derived ok / HTTP / exit code, and its wire schema."""

from __future__ import annotations

import jsonschema
import pytest

from scitex_dev.access import (
    SPEC,
    AccessConfigError,
    AccessDecision,
    AccessRequest,
    Principal,
    Reason,
    decide_unresolved,
    load_decision_schema,
)
from scitex_dev.status import CheckError, StatusCode, is_exchange_id

_REQUEST = AccessRequest(
    principal=Principal.parse("user:bob"), action="edit", resource="demo.doc:/users/alice/d1"
)


def _decision(reason: Reason, hint: str = "do something about it") -> AccessDecision:
    return AccessDecision(request=_REQUEST, reason=reason, detail="observed detail", hint=hint)


HTTP_CASES = [
    (Reason.OWNER, 200),
    (Reason.PUBLIC, 200),
    (Reason.NOT_VISIBLE, 404),
    (Reason.ROLE_TOO_LOW, 403),
    (Reason.AGENT_CEILING, 403),
    (Reason.OWNER_HAS_NO_ROLE, 403),
    (Reason.TOKEN_SCOPE, 403),
    (Reason.NOT_SIGNED_IN, 401),
    (Reason.NOT_ENTITLED, 403),
    (Reason.ENFORCER_UNREACHABLE, 503),
    (Reason.IDENTITY_UNRESOLVED, 503),
    (Reason.KIND_UNREGISTERED, 500),
]


@pytest.mark.parametrize("reason, expected", HTTP_CASES, ids=[case[0].value for case in HTTP_CASES])
def test_http_status_is_derived_from_the_reason(reason, expected):
    # Arrange
    decision = _decision(reason)
    # Act
    status = decision.http_status
    # Assert
    assert status == expected


EXIT_CASES = [
    (Reason.GRANT, 0),
    (Reason.ROLE_TOO_LOW, 10),
    (Reason.NOT_VISIBLE, 10),
    (Reason.NOT_SIGNED_IN, 10),
    (Reason.NOT_ENTITLED, 10),
    (Reason.AGENT_CEILING, 10),
    (Reason.ENFORCER_UNREACHABLE, 11),
    (Reason.KIND_UNREGISTERED, 11),
]


@pytest.mark.parametrize("reason, expected", EXIT_CASES, ids=[case[0].value for case in EXIT_CASES])
def test_exit_code_is_derived_from_the_decision_kind(reason, expected):
    # Arrange
    decision = _decision(reason)
    # Act
    code = decision.exit_code
    # Assert
    assert code == expected


OK_CASES = [(Reason.GRANT, True), (Reason.ROLE_TOO_LOW, False), (Reason.ENFORCER_UNREACHABLE, None)]


@pytest.mark.parametrize("reason, expected", OK_CASES, ids=[case[0].value for case in OK_CASES])
def test_check_ok_is_three_valued_and_derived(reason, expected):
    # Arrange
    decision = _decision(reason)
    # Act
    wire_ok = decision.to_dict()["check"]["ok"]
    # Assert
    assert wire_ok is expected


@pytest.mark.parametrize("reason", list(Reason), ids=[reason.value for reason in Reason])
def test_every_reason_serialises_to_a_schema_valid_record(reason):
    # Arrange
    record = _decision(reason).to_dict()
    # Act
    validation = jsonschema.validate(record, load_decision_schema())
    # Assert
    assert validation is None


def test_the_record_names_the_access_spec():
    # Arrange
    decision = _decision(Reason.GRANT)
    # Act
    spec = decision.to_dict()["spec"]
    # Assert
    assert spec == SPEC


def test_a_fresh_decision_carries_a_status_exchange_id():
    # Arrange
    decision = _decision(Reason.GRANT)
    # Act
    well_formed = is_exchange_id(decision.exchange_id)
    # Assert
    assert well_formed is True


def test_a_denial_without_a_hint_is_refused_at_construction():
    # Arrange
    kwargs = dict(request=_REQUEST, reason=Reason.ROLE_TOO_LOW, detail="holds read")
    # Act
    raised = pytest.raises(CheckError)
    # Assert
    with raised:
        AccessDecision(**kwargs)


def test_the_derived_fields_are_not_serialised():
    # Arrange
    record = _decision(Reason.ROLE_TOO_LOW).to_dict()
    # Act
    stored = {"ok", "http_status", "exit_code"} & set(record)
    # Assert
    assert stored == set()


def test_decide_unresolved_carries_the_native_cause():
    # Arrange
    cause = StatusCode(kind="http", code=503, message="hub answered 503; retry in 30s")
    # Act
    decision = decide_unresolved(
        Principal.parse("user:bob"), "edit", "demo.doc:/users/alice/d1",
        reason=Reason.ENFORCER_UNREACHABLE, detail="hub grants API did not answer",
        hint="retry, or check `scitex-hub doctor`", cause=cause,
    )
    # Assert
    assert decision.to_dict()["check"]["cause"]["code"] == 503


def test_decide_unresolved_refuses_a_non_unresolved_reason():
    # Arrange
    principal = Principal.parse("user:bob")
    # Act
    raised = pytest.raises(AccessConfigError)
    # Assert
    with raised:
        decide_unresolved(
            principal, "edit", "demo.doc:/x", reason=Reason.ROLE_TOO_LOW,
            detail="not unresolved", hint="n/a",
        )


# EOF
