"""`Violation` — one SK finding and its output formatting.

Extracted from `_audit.py` (pure move, no behaviour change) to mirror the
sibling `_project/` auditor package layout and keep each module within
the repo file-size budget.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._registry import RULES


@dataclass
class Violation:
    rule: str
    where: str
    detail: str

    def format(self) -> str:
        r = RULES.get(self.rule)
        section = r.section if r else "?"
        slug = f" {r.slug}" if r and r.slug else ""
        return f"  [{self.rule} {section}{slug}] {self.where}: {self.detail}"


__all__ = ["Violation"]
