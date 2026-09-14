#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decision kinds and reasons, with their HTTP status and exit code read from ``spec/reasons.yaml``.

The enums are typed out so call sites are checked; the drift test pins them to
the YAML, which stays the source of truth.
"""

from __future__ import annotations

import enum
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..status import Verdict

SPEC = "scitex-access/1"
SPEC_DIR = Path(__file__).with_name("spec")


class DecisionKind(str, enum.Enum):
    """The five answers; the strings match ``scitex_app.authz``'s Verdict kinds."""

    ALLOWED = "allowed"
    DENIED = "denied"
    NOT_SIGNED_IN = "denied-because-not-signed-in"
    NOT_ENTITLED = "denied-because-not-entitled"
    UNRESOLVED = "unresolved"


class Reason(str, enum.Enum):
    OWNER = "owner"
    GRANT = "grant"
    INHERITED = "inherited"
    ORG = "org"
    IMPLIED = "implied"
    PUBLIC = "public"
    NOT_VISIBLE = "not-visible"
    ROLE_TOO_LOW = "role-too-low"
    AGENT_CEILING = "agent-ceiling"
    OWNER_HAS_NO_ROLE = "owner-has-no-role"
    TOKEN_SCOPE = "token-scope"
    NOT_SIGNED_IN = "not-signed-in"
    NOT_ENTITLED = "not-entitled"
    ENFORCER_UNREACHABLE = "enforcer-unreachable"
    IDENTITY_UNRESOLVED = "identity-unresolved"
    KIND_UNREGISTERED = "kind-unregistered"


class AuditReason(str, enum.Enum):
    DRIFT = "drift"


@lru_cache(maxsize=None)
def load_reasons_spec() -> dict[str, Any]:
    import yaml  # local: keeps yaml off the import path of callers that never decide

    path = SPEC_DIR / "reasons.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing; the access decision table is derived from it. "
            "Check [tool.setuptools.package-data] ships access/spec/*.yaml."
        )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def load_decision_schema() -> dict[str, Any]:
    path = SPEC_DIR / "schema" / "access-decision.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _reason_rows() -> dict[str, dict[str, Any]]:
    return {row["reason"]: row for row in load_reasons_spec()["reasons"]}


@lru_cache(maxsize=None)
def _decision_rows() -> dict[str, dict[str, Any]]:
    return {row["kind"]: row for row in load_reasons_spec()["decisions"]}


def decision_kind_of(reason: Reason) -> DecisionKind:
    return DecisionKind(_reason_rows()[reason.value]["decision"])


def http_status_of(reason: Reason) -> int:
    return int(_reason_rows()[reason.value]["http"])


def exit_code_of(kind: DecisionKind) -> int:
    return int(_decision_rows()[kind.value]["exit_code"])


def verdict_of(kind: DecisionKind) -> Verdict:
    return Verdict(_decision_rows()[kind.value]["verdict"])


__all__ = [
    "SPEC",
    "AuditReason",
    "DecisionKind",
    "Reason",
    "decision_kind_of",
    "exit_code_of",
    "http_status_of",
    "load_decision_schema",
    "load_reasons_spec",
    "verdict_of",
]

# EOF
