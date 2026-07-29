"""The `Rule` frozen dataclass for the project-structure auditor.

Extracted from `_registry.py` — pure move, no behaviour change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    code: str
    section: str
    message: str
    # Severity drives the audit's exit code:
    #   E (error)   — at least one E finding fails the audit (exit 1)
    #   W (warning) — printed but does not fail (exit 0 if no E findings)
    #   I (info)    — printed only with --severity info; never fails
    # Default W keeps existing rules backward-compatible until each is
    # explicitly tagged. Promote to E when the rule is well-tested and the
    # ecosystem has already been brought into compliance.
    severity: str = "W"
    # Short kebab-case human-readable name (e.g. "examples-need-finished-success").
    # Surfaces in `audit-all` output as `[CODE §X slug] …` so reviewers can
    # read intent without cross-referencing rule numbers.
    slug: str = ""


__all__ = ["Rule"]

# EOF
