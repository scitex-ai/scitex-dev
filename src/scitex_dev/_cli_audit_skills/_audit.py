"""Static auditor for SciTeX `_skills/<pip-name>/` directories — engine + rules.

Rules cover the automatable items from
`scitex-python/src/scitex/_skills/general/03_interface_04_skills/12_quality-checklist.md`.

Numbering: `SK<§><idx>` (e.g. SK101 = §1 rule 01). Mirrors the `PA<n>` /
`M<n>` rule-numbering used by the sibling `_cli_audit_api` and
`_cli_audit/_mcp_audit` modules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import click


@dataclass(frozen=True)
class Rule:
    code: str
    section: str
    message: str


RULES: dict[str, Rule] = {
    r.code: r
    for r in [
        # §1 Directory structure
        Rule("SK101", "§1", "no `_skills/` directory found in package source"),
        Rule("SK102", "§1", "missing `_skills/<pip-name>/SKILL.md` index file"),
        Rule(
            "SK103",
            "§1",
            "forbidden subdirectory inside `_skills/` (`legacy/` / `.old/`)",
        ),
        Rule(
            "SK104",
            "§1",
            "duplicate index file (e.g. `SKILL_INDEX.md`); only one `SKILL.md` per dir",
        ),
        # §2 File naming & ordering
        Rule(
            "SK201",
            "§2",
            "leaf `.md` lacks a 2-digit zero-padded numeric prefix (e.g. `01_`)",
        ),
        Rule("SK202", "§2", "`SKILL.md` must not carry a numeric prefix"),
        Rule("SK203", "§2", "filename is not kebab-case after the numeric prefix"),
        # §2a Frontmatter must be first bytes (no header/footer)
        Rule(
            "SK210",
            "§2a",
            "file starts with HTML-comment banner (e.g. `<!-- --- Timestamp: ... --- -->`); "
            "frontmatter must be at byte 0",
        ),
        Rule(
            "SK211",
            "§2a",
            "file ends with `<!-- EOF -->` or similar trailing marker",
        ),
        # §3 SKILL.md as index only
        Rule("SK301", "§3", "`SKILL.md` exceeds the size budget (~80 lines / ~4 KB)"),
        Rule(
            "SK302",
            "§3",
            "sibling leaf `.md` is not linked from `SKILL.md` (orphan or dead link)",
        ),
        # §4 Leaf file size — no monolith
        Rule("SK401", "§4", "leaf `.md` exceeds the size budget (~10 KB / ~200 lines)"),
        # §FM Frontmatter required fields (rule SK210 is separate — about position)
        Rule(
            "SK701", "§FM", "file is missing YAML frontmatter (`---` block at line 1)"
        ),
        Rule("SK702", "§FM", "frontmatter is missing required field `name`"),
        Rule("SK703", "§FM", "frontmatter is missing required field `description`"),
        Rule("SK704", "§FM", "frontmatter is missing recommended field `tags`"),
        # §6 No contradictions with general/
        Rule(
            "SK601",
            "§6",
            "skill text uses `import scitex as stx`; ecosystem rule is bare "
            "`import scitex`",
        ),
    ]
}


@dataclass
class Violation:
    rule: str
    where: str
    detail: str

    def format(self) -> str:
        r = RULES.get(self.rule)
        section = r.section if r else "?"
        return f"  [{self.rule} {section}] {self.where}: {self.detail}"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _import_name(distribution: str) -> str:
    """Mirror `_cli_audit_api`: dist -> import name (`-` -> `_`)."""
    return distribution.replace("-", "_")


def _locate_skills_dir(distribution: str) -> Path | None:
    """Return `<pkg>/_skills/<pip-name>/` if it exists, else None.

    Resolution: import the package via `importlib.util.find_spec`, walk to
    `_skills/<distribution>/`. Falls back to `_skills/` flat layout for
    legacy packages (caller decides whether to flag SK102).
    """
    import importlib.util

    import_name = _import_name(distribution)
    spec = importlib.util.find_spec(import_name)
    if spec is None or not spec.submodule_search_locations:
        return None
    for loc in spec.submodule_search_locations:
        candidate = Path(loc) / "_skills" / distribution
        if candidate.is_dir():
            return candidate
        # Fallback: flat _skills/ — caller still gets a path so SK102/SK101
        # distinction is preserved.
        flat = Path(loc) / "_skills"
        if flat.is_dir():
            return flat
    return None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

_LEAF_PREFIX_RE = re.compile(r"^\d{2}_")
_KEBAB_SUFFIX_RE = re.compile(r"^\d{2}_[a-z0-9]+(?:[-_][a-z0-9]+)*\.md$")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_FRONTMATTER_KEY_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*):", re.MULTILINE)
_HTML_HEADER_RE = re.compile(r"\A<!-- ---")
_HTML_FOOTER_RE = re.compile(r"<!-- EOF -->\s*\Z")
_FORBIDDEN_SUBDIRS = {"legacy", ".old"}
_MAX_SKILL_MD_BYTES = 4 * 1024
_MAX_SKILL_MD_LINES = 80
_MAX_LEAF_BYTES = 10 * 1024
_MAX_LEAF_LINES = 200


def _check_layout(
    skills_dir: Path | None,
    distribution: str,
    out: list[Violation],
) -> Path | None:
    """SK101 / SK102 / SK103 / SK104 — directory structure.

    Returns the canonical sub-skill dir (`_skills/<pip-name>/`) for downstream
    checks, or None if SK101/SK102 made further checks impossible.
    """
    if skills_dir is None:
        out.append(Violation("SK101", distribution, "no `_skills/` directory found"))
        return None
    # SK102 — distinguish flat `_skills/` vs `_skills/<pip-name>/`.
    if skills_dir.name == "_skills":
        # flat layout — index missing
        out.append(
            Violation(
                "SK102",
                str(skills_dir),
                f"expected `_skills/{distribution}/SKILL.md`",
            )
        )
        return None
    skill_md = skills_dir / "SKILL.md"
    if not skill_md.is_file():
        out.append(
            Violation(
                "SK102",
                str(skills_dir),
                "missing `SKILL.md` index",
            )
        )
        return None
    # SK103 — forbidden subdirs
    for sub in skills_dir.iterdir():
        if sub.is_dir() and sub.name in _FORBIDDEN_SUBDIRS:
            out.append(
                Violation("SK103", str(sub), f"forbidden subdirectory: {sub.name}/")
            )
    # SK104 — duplicate index files
    aliases = ("SKILL_INDEX.md", "INDEX.md", "README.md")
    for alias in aliases:
        if (skills_dir / alias).is_file():
            out.append(
                Violation(
                    "SK104",
                    str(skills_dir / alias),
                    f"alias index `{alias}` shadows the canonical `SKILL.md`",
                )
            )
    return skills_dir


def _check_naming(skills_dir: Path, out: list[Violation]) -> None:
    """SK201 / SK202 / SK203 — file naming."""
    for f in skills_dir.iterdir():
        if not f.is_file() or f.suffix != ".md":
            continue
        name = f.name
        if name == "SKILL.md":
            continue
        if name in {"TODO.md", "MANIFEST.md", "DRIFT_REPORT.md"}:
            # Project-management leaves are exempt from the prefix rule.
            continue
        if not _LEAF_PREFIX_RE.match(name):
            out.append(Violation("SK201", str(f), "missing `NN_` numeric prefix"))
            continue
        if name.startswith("SKILL"):
            out.append(Violation("SK202", str(f), "`SKILL.md` must not carry a prefix"))
        if not _KEBAB_SUFFIX_RE.match(name):
            out.append(
                Violation(
                    "SK203",
                    str(f),
                    "filename should be `NN_kebab-case.md` lowercase",
                )
            )


def _check_header_footer(path: Path, out: list[Violation]) -> None:
    """SK210 / SK211 — banned header/footer markers."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if _HTML_HEADER_RE.match(text):
        out.append(
            Violation("SK210", str(path), "remove `<!-- --- ... --- -->` banner")
        )
    if _HTML_FOOTER_RE.search(text):
        out.append(Violation("SK211", str(path), "remove trailing `<!-- EOF -->`"))


def _check_frontmatter(path: Path, out: list[Violation]) -> dict[str, str] | None:
    """SK701 / SK702 / SK703 / SK704 — frontmatter required fields.

    Returns the parsed key->raw-value dict for downstream rule reuse, or None
    if frontmatter is missing entirely.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        out.append(Violation("SK701", str(path), "no `---` frontmatter block"))
        return None
    block = m.group(1)
    keys = set(_FRONTMATTER_KEY_RE.findall(block))
    if "name" not in keys:
        out.append(Violation("SK702", str(path), "missing `name:` field"))
    if "description" not in keys:
        out.append(Violation("SK703", str(path), "missing `description:` field"))
    if "tags" not in keys:
        out.append(Violation("SK704", str(path), "missing `tags:` field"))
    return {k: "" for k in keys}


def _check_skill_md_size(skill_md: Path, out: list[Violation]) -> None:
    """SK301 — SKILL.md size budget."""
    nbytes = skill_md.stat().st_size
    nlines = skill_md.read_text().count("\n")
    if nbytes > _MAX_SKILL_MD_BYTES or nlines > _MAX_SKILL_MD_LINES:
        out.append(
            Violation(
                "SK301",
                str(skill_md),
                f"{nbytes} bytes / {nlines} lines (budget: "
                f"{_MAX_SKILL_MD_BYTES} / {_MAX_SKILL_MD_LINES})",
            )
        )


def _check_leaf_size(leaf: Path, out: list[Violation]) -> None:
    """SK401 — leaf size budget."""
    nbytes = leaf.stat().st_size
    nlines = leaf.read_text().count("\n")
    if nbytes > _MAX_LEAF_BYTES or nlines > _MAX_LEAF_LINES:
        out.append(
            Violation(
                "SK401",
                str(leaf),
                f"{nbytes} bytes / {nlines} lines (budget: "
                f"{_MAX_LEAF_BYTES} / {_MAX_LEAF_LINES})",
            )
        )


def _check_index_links(skill_md: Path, skills_dir: Path, out: list[Violation]) -> None:
    """SK302 — every sibling leaf is referenced from SKILL.md (no orphans)."""
    text = skill_md.read_text()
    siblings = {
        f.name
        for f in skills_dir.iterdir()
        if f.is_file() and f.suffix == ".md" and f.name != "SKILL.md"
    }
    for name in sorted(siblings):
        # Look for the literal filename in a markdown link.
        if f"]({name})" not in text and f"({name})" not in text:
            out.append(
                Violation(
                    "SK302",
                    str(skills_dir / name),
                    "leaf is not referenced from `SKILL.md`",
                )
            )


def _check_import_alias(path: Path, out: list[Violation]) -> None:
    """SK601 — skill text must not say `import scitex as stx`."""
    text = path.read_text()
    if re.search(r"\bimport\s+scitex\s+as\s+stx\b", text):
        out.append(
            Violation(
                "SK601",
                str(path),
                "use bare `import scitex` (per general/01_ecosystem rule)",
            )
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def audit_skills(
    distribution: str,
    *,
    json_out: bool = False,
    rules: set[str] | None = None,
) -> int:
    """Audit `<distribution>` against the skills checklist. Warn-only.

    Parameters
    ----------
    distribution : str
        Distribution name (e.g. ``"scitex-io"``).
    json_out : bool
        Emit machine-readable output on stdout.
    rules : set of str, optional
        If given, only run these rule codes.

    Returns
    -------
    int
        Exit code: 0 = no violations, 1 = violations, 2 = could not locate.
    """
    skills_dir = _locate_skills_dir(distribution)
    violations: list[Violation] = []

    canonical_dir = _check_layout(skills_dir, distribution, violations)

    if canonical_dir is not None:
        skill_md = canonical_dir / "SKILL.md"

        # SKILL.md checks.
        _check_header_footer(skill_md, violations)
        _check_frontmatter(skill_md, violations)
        _check_skill_md_size(skill_md, violations)
        _check_index_links(skill_md, canonical_dir, violations)
        _check_import_alias(skill_md, violations)

        # Naming check covers the whole directory at once.
        _check_naming(canonical_dir, violations)

        # Per-leaf checks.
        for leaf in sorted(canonical_dir.iterdir()):
            if not leaf.is_file() or leaf.suffix != ".md" or leaf.name == "SKILL.md":
                continue
            _check_header_footer(leaf, violations)
            _check_frontmatter(leaf, violations)
            _check_leaf_size(leaf, violations)
            _check_import_alias(leaf, violations)

    if rules:
        violations = [v for v in violations if v.rule in rules]

    if json_out:
        import json

        click.echo(
            json.dumps(
                {
                    "distribution": distribution,
                    "skills_dir": str(skills_dir) if skills_dir else None,
                    "violations": [
                        {"rule": v.rule, "where": v.where, "detail": v.detail}
                        for v in violations
                    ],
                },
                indent=2,
            )
        )
        return 0 if not violations else 1

    if skills_dir is None:
        click.echo(
            f"audit-skills: cannot locate `_skills/` for '{distribution}' "
            "(is it installed?)",
            err=True,
        )
        return 2

    if not violations:
        click.echo(f"ok  {distribution}: no skills violations")
        return 0

    click.echo(f"warn  {distribution}: {len(violations)} violation(s)")
    for v in violations:
        click.echo(v.format())
    return 1
