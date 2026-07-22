"""Per-file SK checks (layout, naming, frontmatter, size, imports).

Extracted from `_audit.py` (pure move, no behaviour change) to mirror the
sibling `_project/` auditor package layout and keep each module within
the repo file-size budget.
"""

from __future__ import annotations

import re
from pathlib import Path

from ...._ecosystem._skills import skills_audit_core as _core
from ._violation import Violation

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_FRONTMATTER_KEY_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*):", re.MULTILINE)
_HTML_HEADER_RE = re.compile(r"\A<!-- ---")
_HTML_FOOTER_RE = re.compile(r"<!-- EOF -->\s*\Z")
_MAX_SKILL_MD_BYTES = 6 * 1024
_MAX_SKILL_MD_LINES = 120
_MAX_LEAF_BYTES = 10 * 1024
_MAX_LEAF_LINES = 200
_NAMING_EXEMPT = {"TODO.md", "DRIFT_REPORT.md"}


def _check_layout(
    skills_dir: Path | None,
    distribution: str,
    out: list[Violation],
) -> Path | None:
    """SK-101 / SK-102 / SK-103 / SK-104 — directory structure.

    Returns the canonical sub-skill dir (`_skills/<pip-name>/`) for downstream
    checks, or None if SK-101/SK-102 made further checks impossible.
    """
    if skills_dir is None:
        out.append(Violation("SK-101", distribution, "no `_skills/` directory found"))
        return None
    # SK-102 — distinguish flat `_skills/` vs `_skills/<pip-name>/`.
    if skills_dir.name == "_skills":
        # flat layout — index missing
        out.append(
            Violation(
                "SK-102",
                str(skills_dir),
                f"expected `_skills/{distribution}/SKILL.md`",
            )
        )
        return None
    skill_md = skills_dir / "SKILL.md"
    if not skill_md.is_file():
        out.append(
            Violation(
                "SK-102",
                str(skills_dir),
                "missing `SKILL.md` index",
            )
        )
        return None
    # SK-103 — forbidden subdirs
    for sub in _core.find_forbidden_subdirs(skills_dir):
        out.append(
            Violation("SK-103", str(sub), f"forbidden subdirectory: {sub.name}/")
        )
    # SK-104 — duplicate index files
    aliases = ("SKILL_INDEX.md", "INDEX.md", "README.md")
    for alias_path in _core.find_alias_indexes(skills_dir, aliases):
        out.append(
            Violation(
                "SK-104",
                str(alias_path),
                f"alias index `{alias_path.name}` shadows the canonical `SKILL.md`",
            )
        )
    # SK-105 — MANIFEST.md is forbidden. The canonical index is SKILL.md;
    # distribution / update mechanics belong in a numbered leaf or the
    # package README.
    manifest = skills_dir / "MANIFEST.md"
    if manifest.is_file():
        out.append(
            Violation(
                "SK-105",
                str(manifest),
                "`MANIFEST.md` is forbidden — fold its content into a "
                "numbered leaf (e.g. `99_distribution.md`) or the README; "
                "`SKILL.md` is the single canonical index",
            )
        )
    return skills_dir


def _check_naming(skills_dir: Path, out: list[Violation]) -> None:
    """SK-201 / SK-202 / SK-203 — file naming."""
    for f in skills_dir.iterdir():
        if not f.is_file() or f.suffix != ".md":
            continue
        name = f.name
        if name == "SKILL.md":
            continue
        if name in _NAMING_EXEMPT:
            # Project-management leaves are exempt from the prefix rule.
            continue
        if not _core.has_numeric_prefix(name):
            out.append(Violation("SK-201", str(f), "missing `NN_` numeric prefix"))
            continue
        if name.startswith("SKILL"):
            out.append(
                Violation("SK-202", str(f), "`SKILL.md` must not carry a prefix")
            )
        if not _core.is_kebab_after_prefix(name):
            out.append(
                Violation(
                    "SK-203",
                    str(f),
                    "filename should be `NN_kebab-case.md` lowercase",
                )
            )


def _check_header_footer(path: Path, out: list[Violation]) -> None:
    """SK-210 / SK-211 — banned header/footer markers."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if _HTML_HEADER_RE.match(text):
        out.append(
            Violation("SK-210", str(path), "remove `<!-- --- ... --- -->` banner")
        )
    if _HTML_FOOTER_RE.search(text):
        out.append(Violation("SK-211", str(path), "remove trailing `<!-- EOF -->`"))


def _check_frontmatter(
    path: Path, out: list[Violation], *, is_skill_md: bool = True
) -> dict[str, str] | None:
    """SK-701 / SK-702 / SK-703 / SK-704 — frontmatter required fields.

    SK-702 (`name:` required) only fires for SKILL.md; leaves are governed by
    SK-705 (must NOT carry `name:`).

    Returns the parsed key->raw-value dict for downstream rule reuse, or None
    if frontmatter is missing entirely.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        out.append(Violation("SK-701", str(path), "no `---` frontmatter block"))
        return None
    block = m.group(1)
    keys = set(_FRONTMATTER_KEY_RE.findall(block))
    if is_skill_md and "name" not in keys:
        out.append(Violation("SK-702", str(path), "missing `name:` field"))
    if "description" not in keys:
        out.append(Violation("SK-703", str(path), "missing `description:` field"))
    if "tags" not in keys:
        out.append(Violation("SK-704", str(path), "missing `tags:` field"))
    return {k: "" for k in keys}


def _check_skill_md_size(skill_md: Path, out: list[Violation]) -> None:
    """SK-301 — SKILL.md size budget."""
    nbytes, nlines = _core.file_size(skill_md)
    if nbytes > _MAX_SKILL_MD_BYTES or nlines > _MAX_SKILL_MD_LINES:
        out.append(
            Violation(
                "SK-301",
                str(skill_md),
                f"{nbytes} bytes / {nlines} lines (budget: "
                f"{_MAX_SKILL_MD_BYTES} / {_MAX_SKILL_MD_LINES})",
            )
        )


def _check_leaf_size(leaf: Path, out: list[Violation]) -> None:
    """SK-401 — leaf size budget."""
    nbytes, nlines = _core.file_size(leaf)
    if nbytes > _MAX_LEAF_BYTES or nlines > _MAX_LEAF_LINES:
        out.append(
            Violation(
                "SK-401",
                str(leaf),
                f"{nbytes} bytes / {nlines} lines (budget: "
                f"{_MAX_LEAF_BYTES} / {_MAX_LEAF_LINES})",
            )
        )


def _check_index_links(skill_md: Path, skills_dir: Path, out: list[Violation]) -> None:
    """SK-302 — every sibling leaf is referenced from SKILL.md (no orphans)."""
    for orphan in _core.find_orphan_leaves(skill_md, skills_dir):
        out.append(
            Violation(
                "SK-302",
                str(orphan),
                "leaf is not referenced from `SKILL.md`",
            )
        )


def _check_import_alias(path: Path, out: list[Violation]) -> None:
    """SK-601 — skill text must not say `import scitex as stx`."""
    text = path.read_text()
    if re.search(r"\bimport\s+scitex\s+as\s+stx\b", text):
        out.append(
            Violation(
                "SK-601",
                str(path),
                "use bare `import scitex` (per general/01_ecosystem rule)",
            )
        )


__all__ = [
    "_check_frontmatter",
    "_check_header_footer",
    "_check_import_alias",
    "_check_index_links",
    "_check_layout",
    "_check_leaf_size",
    "_check_naming",
    "_check_skill_md_size",
]
