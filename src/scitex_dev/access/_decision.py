#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``AccessDecision`` — the one feedback record every access answer travels in.

It WRAPS the status types rather than extending them: ``check`` is a real
``scitex_dev.status.Check`` (whose schema is closed), and ``ok``, the HTTP
status and the exit code are derived from (kind, reason), never stored.

Wire form::

    {"spec": "scitex-access/1",
     "exchange_id": "xch_...",
     "decision": {"kind": "denied", "role": "read", "required_role": "write"},
     "reason": "role-too-low",
     "check": {"name": "access", "ok": false, "detail": "...", "hint": "..."},
     "request": {"principal": "user:bob", "action": "edit", "resource": "k:/p"}}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..scope import Role
from ..status import Check, StatusCode, Verdict, new_exchange_id
from ._errors import AccessDenied, AccessUnresolved
from ._reasons import (
    SPEC,
    DecisionKind,
    Reason,
    decision_kind_of,
    exit_code_of,
    http_status_of,
    verdict_of,
)
from ._types import AccessRequest

CHECK_NAME = "access"


@dataclass(frozen=True, kw_only=True)
class AccessDecision:
    request: AccessRequest
    reason: Reason
    detail: str
    hint: Optional[str] = None
    role: Optional[Role] = None
    required_role: Optional[Role] = None
    cause: Optional[StatusCode] = None
    exchange_id: str = ""

    def __post_init__(self) -> None:
        if not self.exchange_id:
            object.__setattr__(self, "exchange_id", new_exchange_id())
        # Building the Check here enforces its rules (a not-ok needs a hint) at construction.
        self.check

    @property
    def kind(self) -> DecisionKind:
        return decision_kind_of(self.reason)

    @property
    def verdict(self) -> Verdict:
        return verdict_of(self.kind)

    @property
    def ok(self) -> Optional[bool]:
        return self.verdict.ok

    @property
    def is_allowed(self) -> bool:
        return self.kind is DecisionKind.ALLOWED

    @property
    def http_status(self) -> int:
        return http_status_of(self.reason)

    @property
    def exit_code(self) -> int:
        return exit_code_of(self.kind)

    @property
    def check(self) -> Check:
        return Check(
            name=CHECK_NAME,
            verdict=self.verdict,
            detail=self.detail,
            hint=self.hint,
            cause=self.cause,
        )

    def raise_if_not_allowed(self) -> "AccessDecision":
        if self.kind is DecisionKind.UNRESOLVED:
            raise AccessUnresolved(f"{self.reason.value}: {self.detail}", self)
        if self.kind is not DecisionKind.ALLOWED:
            raise AccessDenied(self)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": SPEC,
            "exchange_id": self.exchange_id,
            "decision": {
                "kind": self.kind.value,
                "role": self.role,
                "required_role": self.required_role,
            },
            "reason": self.reason.value,
            "check": self.check.to_dict(),
            "request": self.request.to_dict(),
        }


__all__ = ["CHECK_NAME", "AccessDecision"]

# EOF
