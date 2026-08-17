#!/usr/bin/env python3
"""The skills verdict must state WHAT IT INSPECTED, not only what it found.

`no skills violations` used to read identically whether forty leaves were
checked or the directory was empty — the empty case rendering as the clean
case. This is the same defect `_summary/_coverage.py` removed for audit-cli
on 2026-07-29 and #654 removed for audit-python-apis; the skills leg was the
last one reporting a verdict with no scope.

A separate file from `test__audit.py` deliberately: that one is 694 lines,
already over the 512-line cap, and appending to it would grow a file that
needs splitting rather than adding a cohesive small one.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._skills._audit import _collect_violations


def _skills_tree(tmp_path: Path, leaves: tuple[str, ...]) -> Path:
    """A canonical skills dir with SKILL.md plus the named leaves."""
    canonical = tmp_path / "skills" / "fakepkg"
    canonical.mkdir(parents=True)
    (canonical / "SKILL.md").write_text("# fakepkg\n")
    for name in leaves:
        (canonical / name).write_text(f"# {name}\n")
    return canonical


def test_each_checked_leaf_is_counted(tmp_path):
    # Arrange
    canonical = _skills_tree(tmp_path, ("01_a.md", "02_b.md", "03_c.md"))
    # Act
    inspected: set[Path] = set()
    _collect_violations("fakepkg", canonical, inspected)
    # Assert
    assert len(inspected) == 3


def test_skill_md_is_not_counted_as_a_leaf(tmp_path):
    """SKILL.md is the index, not a leaf, and the loop skips it.

    Counted at the point PAST the skip, so the denominator reports leaves
    actually CHECKED rather than directory entries encountered.
    """
    # Arrange
    canonical = _skills_tree(tmp_path, ())
    # Act
    inspected: set[Path] = set()
    _collect_violations("fakepkg", canonical, inspected)
    # Assert
    assert inspected == set()


def test_non_markdown_entries_are_not_counted(tmp_path):
    """A directory of non-skill files must not read as coverage.

    Otherwise a tree containing only `data.json` would report a non-zero
    denominator and license a verdict over nothing.
    """
    # Arrange
    canonical = _skills_tree(tmp_path, ("01_real.md",))
    (canonical / "data.json").write_text("{}\n")
    (canonical / "notes.txt").write_text("x\n")
    # Act
    inspected: set[Path] = set()
    _collect_violations("fakepkg", canonical, inspected)
    # Assert
    assert len(inspected) == 1


def test_the_denominator_is_optional_so_existing_callers_keep_working(tmp_path):
    # Arrange
    canonical = _skills_tree(tmp_path, ("01_a.md",))
    # Act
    violations = _collect_violations("fakepkg", canonical)
    # Assert
    assert isinstance(violations, list)


# EOF
