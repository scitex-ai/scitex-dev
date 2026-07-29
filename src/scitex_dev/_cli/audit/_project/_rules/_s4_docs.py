"""§4 docs/ structure rules.

Rule literals extracted verbatim from `_registry.py` (1286 lines, cap 512)
— pure move, no behaviour change. The corpus ASSEMBLY (severity/slug
tables, co-located merges, the final `_patch` apply) deliberately stays
together in `_rules/__init__.py`. See GITIGNORED/REFACTORING.md.
"""

from __future__ import annotations

from ._rule import Rule

RULES_S4_DOCS: list[Rule] = [
        # §4 docs/ structure ----------------------------------------------------
        Rule(
            "PS-401",
            "§4",
            "./docs/to_claude/ is tracked — must be gitignored (local-machine agent context, not part of the shipped repo)",
        ),
        Rule(
            "PS-402",
            "§4",
            "top-level ./assets/ exists — figures/screenshots belong under ./docs/assets/",
        ),
]

# EOF
