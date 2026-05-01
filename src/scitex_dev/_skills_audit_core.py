"""Shared, side-effect-free helpers for skill-directory auditors.

Two public auditors live above this module:

* `_skills_quality` — repo-rooted, used by downstream `tests/test_skills_quality.py`.
* `_cli_audit_skills._audit` — distribution-rooted CLI auditor.

They wrap the same underlying checks in different report shapes (`SkillIssue`
vs `Violation`) and use different rule code styles (`§X.name` vs `SK<n>`),
so this core layer returns plain data (paths, ints, tuples) and lets each
adapter format its own violations.

Each adapter still owns its own thresholds (`INDEX_SIZE_MAX`, `LEAF_SIZE_MAX`,
…) so size-budget tuning stays decoupled.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_MD = "SKILL.md"
FORBIDDEN_SUBDIRS = frozenset({"legacy", ".old"})
SYSTEM_FILES = frozenset({"MANIFEST.md"})

# Filename prefix:
#   2-level: NN_kebab-name.md                       (e.g. 40_playground.md)
#   3-level: NN_<group>_NN_<leaf>.md                (e.g. 01_ecosystem_01_upstream-and-downstream.md)
PREFIX_RE = re.compile(
    r"^(\d{2})_[a-z0-9][a-z0-9-]*"
    r"(?:_(\d{2})_[a-z0-9][a-z0-9-]*)?"
    r"\.md$"
)
LEAF_PREFIX_RE = re.compile(r"^\d{2}_")
KEBAB_AFTER_PREFIX_RE = re.compile(r"^\d{2}_[a-z0-9]+(?:[-_][a-z0-9]+)*\.md$")


def parse_prefix(name: str) -> tuple[int, int | None] | None:
    """Return ``(group, leaf|None)`` for a valid skill leaf filename, else ``None``."""
    m = PREFIX_RE.match(name)
    if not m:
        return None
    group = int(m.group(1))
    leaf = int(m.group(2)) if m.group(2) else None
    return group, leaf


def has_numeric_prefix(name: str) -> bool:
    return bool(LEAF_PREFIX_RE.match(name))


def is_kebab_after_prefix(name: str) -> bool:
    return bool(KEBAB_AFTER_PREFIX_RE.match(name))


def iter_leaves(skills_dir: Path) -> list[Path]:
    """Return sorted sub-skill leaves (excludes ``SKILL.md`` and ``SYSTEM_FILES``)."""
    return sorted(
        p
        for p in skills_dir.iterdir()
        if p.is_file()
        and p.suffix == ".md"
        and p.name != SKILL_MD
        and p.name not in SYSTEM_FILES
    )


def file_size(path: Path) -> tuple[int, int]:
    """Return ``(bytes, line_count)``."""
    nbytes = path.stat().st_size
    nlines = path.read_text(errors="replace").count("\n")
    return nbytes, nlines


def find_forbidden_subdirs(skills_dir: Path) -> list[Path]:
    return [
        p for p in skills_dir.iterdir() if p.is_dir() and p.name in FORBIDDEN_SUBDIRS
    ]


def find_alias_indexes(skills_dir: Path, aliases: tuple[str, ...]) -> list[Path]:
    return [skills_dir / a for a in aliases if (skills_dir / a).is_file()]


def find_orphan_leaves(skill_md: Path, skills_dir: Path) -> list[Path]:
    """Leaves whose filename does not appear in ``SKILL.md``."""
    text = skill_md.read_text(errors="replace")
    return [leaf for leaf in iter_leaves(skills_dir) if leaf.name not in text]


def find_dead_links(skill_md: Path, skills_dir: Path) -> list[str]:
    """Markdown ``.md`` links in ``SKILL.md`` whose target sibling is missing.

    Cross-directory links (containing ``/``) are skipped — they may resolve
    to another package or a sub-folder structure handled elsewhere.
    """
    text = skill_md.read_text(errors="replace")
    missing: list[str] = []
    # Require ']' immediately before '(' so we ONLY match markdown link
    # syntax `[text](url.md)` and not arbitrary parentheticals like
    # `(see [foo.md](foo.md))` which would otherwise greedily capture
    # past the inner `]` and produce a bogus "missing" target.
    for m in re.finditer(r"\]\(([^)]+\.md)\)", text):
        target = m.group(1)
        if "/" in target:
            continue
        if not (skills_dir / target).exists():
            missing.append(target)
    return missing


def find_duplicate_prefixes(skills_dir: Path) -> list[tuple[int, int | None]]:
    """Return prefix keys that appear on more than one leaf in ``skills_dir``.

    For 2-level names the key is ``(group, None)``; for 3-level names it is
    ``(group, leaf)``. Different leaves under the same group (e.g.
    ``01_ecosystem_01_*``, ``01_ecosystem_02_*``) do not collide.
    """
    keys: list[tuple[int, int | None]] = []
    for leaf in iter_leaves(skills_dir):
        k = parse_prefix(leaf.name)
        if k is not None:
            keys.append(k)
    seen: set[tuple[int, int | None]] = set()
    dupes: list[tuple[int, int | None]] = []
    for k in keys:
        if keys.count(k) > 1 and k not in seen:
            seen.add(k)
            dupes.append(k)
    return dupes
