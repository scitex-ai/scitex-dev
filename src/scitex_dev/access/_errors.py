#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The three ways an access question surfaces as a Python exception.

Each subclasses the builtin a caller would already catch, so adopting the
primitive does not require new ``except`` clauses to stay correct.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ._decision import AccessDecision


class AccessDenied(PermissionError):
    """A definite no: denied, not signed in, or not entitled."""

    def __init__(self, decision: "AccessDecision") -> None:
        super().__init__(f"{decision.kind}/{decision.reason}: {decision.detail}")
        self.decision = decision


class AccessUnresolved(RuntimeError):
    """The question could not be answered. Never a synonym for denied."""

    def __init__(self, message: str, decision: "Optional[AccessDecision]" = None) -> None:
        super().__init__(message)
        self.decision = decision


class AccessConfigError(ValueError):
    """A malformed principal, grant, kind or fixture: a bug in the caller, not an answer."""


__all__ = ["AccessConfigError", "AccessDenied", "AccessUnresolved"]

# EOF
