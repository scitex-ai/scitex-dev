"""Programmatic checks for the SciTeX skills quality checklist.

Canonical rules: src/scitex/_skills/general/21_scitex-package-quality-checklist.md
"""

from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass, field
import re

SKILL_MD = "SKILL.md"
LEAF_SIZE_MAX = 16 * 1024  # §4 — dense reference leaves can run ~12-15KB
STUB_SIZE_MIN = 300  # §4
INDEX_SIZE_MAX = 8 * 1024  # §3 — accommodates ~25 entries with descriptions
# Matches either:
#   2-level: NN_kebab-name.md                       (e.g. 40_playground.md)
#   3-level: NN_group-kebab_NN_leaf-kebab.md        (e.g. 01_ecosystem_01_upstream-and-downstream.md)
PREFIX_RE = re.compile(
    r"^(\d{2})_[a-z0-9][a-z0-9-]*"
    r"(?:_(\d{2})_[a-z0-9][a-z0-9-]*)?"
    r"\.md$"
)
FORBIDDEN_SUBDIRS = {"legacy", ".old"}
ALIAS_INDEX_NAMES = {"SKILL_INDEX.md", "INDEX.md"}
# Special system files that sit alongside SKILL.md but are not content leaves.
# MANIFEST.md carries the version/source stamp written at export time.
SYSTEM_FILES = {"MANIFEST.md"}


@dataclass
class SkillIssue:
    rule: str  # e.g. "§2.prefix"
    path: Path
    message: str


@dataclass
class SkillReport:
    skill_dir: Path
    issues: list[SkillIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def check_skill_dir(skill_dir: Path) -> SkillReport:
    """Validate one sub-skill directory (contains SKILL.md + leaves)."""
    report = SkillReport(skill_dir=skill_dir)
    add = lambda rule, p, msg: report.issues.append(SkillIssue(rule, p, msg))

    # §1 exactly one SKILL.md
    skill_md = skill_dir / SKILL_MD
    if not skill_md.is_file():
        add("§1.index", skill_dir, "missing SKILL.md")
        return report

    # §1 no alias index
    for alias in ALIAS_INDEX_NAMES:
        p = skill_dir / alias
        if p.is_file():
            add("§1.dual-index", p, f"forbidden alias index")

    # §1 no legacy / .old
    for sub in skill_dir.iterdir():
        if sub.is_dir() and sub.name in FORBIDDEN_SUBDIRS:
            add("§1.legacy-dir", sub, "forbidden legacy/.old directory shipped")

    # §3 SKILL.md size
    idx_size = skill_md.stat().st_size
    if idx_size > INDEX_SIZE_MAX:
        add("§3.index-monolith", skill_md, f"{idx_size}B > {INDEX_SIZE_MAX}B")

    # Collect leaves (exclude SKILL.md and system files like MANIFEST.md)
    leaves = sorted(
        p
        for p in skill_dir.iterdir()
        if p.is_file()
        and p.suffix == ".md"
        and p.name != SKILL_MD
        and p.name not in SYSTEM_FILES
    )

    # §2 prefix format. For 2-level names the prefix is a single int;
    # for 3-level names (NN_group_NN_leaf) it is the (group, leaf) pair.
    # Duplicate detection compares full keys so different leaves under the
    # same group (e.g. 01_ecosystem_01_*, 01_ecosystem_02_*) don't collide.
    prefixes_seen: list[tuple[int, int | None]] = []
    for leaf in leaves:
        m = PREFIX_RE.match(leaf.name)
        if not m:
            add("§2.prefix", leaf, "filename must match NN_kebab-name.md")
        else:
            group_prefix = int(m.group(1))
            leaf_prefix = int(m.group(2)) if m.group(2) else None
            prefixes_seen.append((group_prefix, leaf_prefix))

    # §2 duplicate prefixes
    dupes = {key for key in prefixes_seen if prefixes_seen.count(key) > 1}
    for group_p, leaf_p in dupes:
        label = f"{group_p:02d}" if leaf_p is None else f"{group_p:02d}_*_{leaf_p:02d}"
        add("§2.duplicate-prefix", skill_dir, f"prefix {label} used more than once")

    # §4 leaf size
    for leaf in leaves:
        size = leaf.stat().st_size
        if size > LEAF_SIZE_MAX:
            add("§4.monolith", leaf, f"{size}B > {LEAF_SIZE_MAX}B")
        elif size < STUB_SIZE_MIN and "TODO" not in leaf.read_text(errors="ignore"):
            add("§4.stub", leaf, f"{size}B < {STUB_SIZE_MIN}B without TODO marker")

    # §3 every leaf listed in SKILL.md
    index_text = skill_md.read_text(errors="ignore")
    for leaf in leaves:
        if leaf.name not in index_text:
            add("§3.missing-in-index", leaf, "leaf not referenced from SKILL.md")

    # §3 no dead links (naive: every .md filename in SKILL.md must exist)
    for m in re.finditer(r"\(([^)]+\.md)\)", index_text):
        target = m.group(1)
        if "/" in target:  # relative path to another pkg — skip
            continue
        if not (skill_dir / target).exists():
            add("§3.dead-link", skill_md, f"SKILL.md references missing {target}")

    return report


def find_skill_dirs(package_root: Path) -> list[Path]:
    """Locate every sub-skill dir under `<package>/src/*/_skills/*/`."""
    results: list[Path] = []
    for skills_root in (package_root / "src").glob("*/_skills"):
        for sub in skills_root.iterdir():
            if sub.is_dir() and (sub / SKILL_MD).is_file():
                results.append(sub)
    return results


def check_package(package_root: Path) -> list[SkillReport]:
    return [check_skill_dir(d) for d in find_skill_dirs(package_root)]
