"""Violation dataclass for the project-structure auditor.

Split out of `_audit.py` (issue #103) — pure refactor, no behaviour change.
Re-exported from `_audit` for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._registry import RULES


@dataclass
class Violation:
    rule: str
    where: str
    detail: str
    # Per-instance severity override. ``None`` (the default) means "use the
    # rule's registered severity" (unchanged behaviour). A concrete check
    # MAY set this after construction to promote/demote a single finding —
    # e.g. PS-214/PS-215 escalate a NEW (vs. baseline) violation to "E"
    # while a pre-existing one stays at the rule's default "W". See
    # `_new_vs_baseline.escalate_new_violations`.
    severity_override: str | None = None

    def format(self) -> str:
        r = RULES.get(self.rule)
        section = r.section if r else "?"
        sev = self.severity
        slug = f" {r.slug}" if r and r.slug else ""
        return f"  [{sev}] [{self.rule} {section}{slug}] {self.where}: {self.detail}"

    @property
    def severity(self) -> str:
        if self.severity_override:
            return self.severity_override
        r = RULES.get(self.rule)
        return r.severity if r else "W"
