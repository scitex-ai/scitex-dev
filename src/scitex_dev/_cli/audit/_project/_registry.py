"""Rule registry for the project-structure auditor (thin re-export).

The corpus moved to `._rules` — this module blew the 512-line cap at 1286
lines, having already spawned two generations of sidecar
(`_extra_rules.py`, then per-check co-located tuples) for the same reason.
A 1286-line corpus is also how PS-140's remediation text kept telling
readers to run a script in `/tmp` that shipped nowhere: nobody reads 1286
lines to review one string. See GITIGNORED/REFACTORING.md.

Kept as a re-export so every existing `from ._registry import RULES, Rule`
call site keeps working unchanged. `_SEVERITY_OVERRIDES` / `_SLUGS` /
`_patch` are re-exported too — they are private, but the audit test suite
reaches for them by name.
"""

from __future__ import annotations

from ._rules import (  # noqa: F401
    _SEVERITY_OVERRIDES,
    _SLUGS,
    _patch,
    RULES,
    Rule,
)

__all__ = ["RULES", "Rule"]

# EOF
