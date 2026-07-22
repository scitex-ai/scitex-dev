"""SK rule corpus — `Rule` + the `RULES` registry (incl. the v2 merge).

Extracted from `_audit.py` (pure move, no behaviour change) to mirror the
sibling `_project/` auditor package layout and keep each module within
the repo file-size budget.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import _audit_v2 as _v2


@dataclass(frozen=True)
class Rule:
    code: str
    section: str
    message: str
    slug: str = ""  # short kebab-case human-readable name


RULES: dict[str, Rule] = {
    r.code: r
    for r in [
        # §1 Directory structure
        Rule("SK-101", "§1", "no `_skills/` directory found in package source"),
        Rule("SK-102", "§1", "missing `_skills/<pip-name>/SKILL.md` index file"),
        Rule(
            "SK-103",
            "§1",
            "forbidden subdirectory inside `_skills/` (`legacy/` / `.old/`)",
        ),
        Rule(
            "SK-104",
            "§1",
            "duplicate index file (e.g. `SKILL_INDEX.md`); only one `SKILL.md` per dir",
        ),
        Rule(
            "SK-105",
            "§1",
            "`MANIFEST.md` is forbidden — `SKILL.md` is the single canonical "
            "index of every skill tree. Distribution / update mechanics belong "
            "in a numbered leaf (e.g. `99_distribution.md`) or in the package "
            "README, not in a sibling top-level file that duplicates SKILL.md's "
            "intent.",
        ),
        # §2 File naming & ordering
        Rule(
            "SK-201",
            "§2",
            "leaf `.md` lacks a 2-digit zero-padded numeric prefix (e.g. `01_`)",
        ),
        Rule("SK-202", "§2", "`SKILL.md` must not carry a numeric prefix"),
        Rule("SK-203", "§2", "filename is not kebab-case after the numeric prefix"),
        # §2a Frontmatter must be first bytes (no header/footer)
        Rule(
            "SK-210",
            "§2a",
            "file starts with HTML-comment banner (e.g. `<!-- --- Timestamp: ... --- -->`); "
            "frontmatter must be at byte 0",
        ),
        Rule(
            "SK-211",
            "§2a",
            "file ends with `<!-- EOF -->` or similar trailing marker",
        ),
        # §3 SKILL.md as index only
        Rule("SK-301", "§3", "`SKILL.md` exceeds the size budget (~120 lines / ~6 KB)"),
        Rule(
            "SK-302",
            "§3",
            "sibling leaf `.md` is not linked from `SKILL.md` (orphan or dead link)",
        ),
        # §4 Leaf file size — no monolith
        Rule(
            "SK-401", "§4", "leaf `.md` exceeds the size budget (~10 KB / ~200 lines)"
        ),
        # §FM Frontmatter required fields (rule SK-210 is separate — about position)
        Rule(
            "SK-701", "§FM", "file is missing YAML frontmatter (`---` block at line 1)"
        ),
        Rule("SK-702", "§FM", "frontmatter is missing required field `name`"),
        Rule("SK-703", "§FM", "frontmatter is missing required field `description`"),
        Rule("SK-704", "§FM", "frontmatter is missing recommended field `tags`"),
        # §6 No contradictions with general/
        Rule(
            "SK-601",
            "§6",
            "skill text uses `import scitex as stx`; ecosystem rule is bare "
            "`import scitex`",
        ),
    ]
}
# Merge spec-v2 rules (SK-105–SK-111, SK-705–SK-711) — kept in `_audit_v2.py`
# to preserve `_audit.py`'s size budget.
for _r in _v2.V2_RULES.values():
    RULES[_r.code] = Rule(_r.code, _r.section, _r.message)


# Backfill kebab-case slugs across the SK corpus. Surfaced inline in audit
# output as `[SKxxx §X slug] …`. Missing entries fall back to the bare form;
# new rules SHOULD include `slug=...` from definition.
_SLUGS: dict[str, str] = {
    "SK-101": "skills-dir-missing",
    "SK-102": "skill-md-missing",
    "SK-103": "forbidden-skills-subdir",
    "SK-104": "duplicate-skill-index",
    # SK-105 in v2 means "missing 01_installation.md" (overrides the legacy
    # "MANIFEST.md forbidden" rule via the V2 merge above).
    "SK-105": "leaf-installation-missing",
    "SK-106": "leaf-quick-start-missing",
    "SK-107": "leaf-python-api-missing",
    "SK-108": "leaf-cli-reference-missing",
    "SK-109": "leaf-mcp-tools-missing",
    "SK-110": "leaf-http-api-missing",
    "SK-111": "leaf-skill-table-missing",
    "SK-705": "frontmatter-name-mismatch",
    "SK-706": "frontmatter-description-too-short",
    "SK-707": "frontmatter-tags-empty",
    "SK-708": "frontmatter-tags-not-kebab",
    "SK-709": "frontmatter-tags-pkg-prefix-missing",
    "SK-710": "frontmatter-tags-canonical-mismatch",
    "SK-711": "frontmatter-extra-fields",
    "SK-201": "leaf-missing-numeric-prefix",
    "SK-202": "skill-md-with-numeric-prefix",
    "SK-203": "filename-not-kebab-case",
    "SK-210": "frontmatter-not-at-start",
    "SK-211": "trailing-eof-marker",
    "SK-301": "skill-md-over-budget",
    "SK-302": "leaf-not-linked-from-skill-md",
    "SK-401": "leaf-over-budget",
    "SK-601": "scitex-as-stx-import",
    "SK-701": "frontmatter-missing",
    "SK-702": "frontmatter-name-missing",
    "SK-703": "frontmatter-description-missing",
    "SK-704": "frontmatter-tags-missing",
}
RULES = {
    code: (
        Rule(rule.code, rule.section, rule.message, _SLUGS.get(code, ""))
        if not rule.slug and code in _SLUGS
        else rule
    )
    for code, rule in RULES.items()
}


__all__ = ["RULES", "Rule"]
