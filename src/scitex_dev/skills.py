#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skills aggregation across the SciTeX ecosystem.

Each package places skills as markdown files inside its source tree:
    src/<import_name>/skills/<package-name>/SKILL.md
    src/<import_name>/skills/<package-name>/references/*.md

Discovery uses entry points (scitex_dev.skills), falling back to
the ECOSYSTEM registry — same pattern as docs discovery.

Usage:
    from scitex_dev.skills import list_skills, get_skill, get_skill_dir

    # List all skills across ecosystem
    list_skills()

    # List skills for a specific package
    list_skills(package="scitex-stats")

    # Get main SKILL.md content
    get_skill(package="scitex-stats")

    # Get a reference page
    get_skill(package="scitex-stats", name="test-selection")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ._discovery import discover_packages, get_package_root

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "scitex_dev.skills"


def _find_skills_dir(module_name: str, pip_name: str) -> Optional[Path]:
    """Find the skills directory for a package.

    Resolution chain:
        1. Installed package: <pkg_root>/skills/<pip-name>/
        2. Legacy location: <pkg_root>/docs/MASTER/skills/
    """
    root = get_package_root(module_name)
    if root is None:
        return None

    # Primary: inside the package (ships with pip install)
    skills_dir = root / "skills" / pip_name
    if skills_dir.is_dir() and (skills_dir / "SKILL.md").exists():
        return skills_dir

    # Fallback: legacy docs/MASTER/skills/
    legacy_dir = root / "docs" / "MASTER" / "skills"
    if legacy_dir.is_dir():
        return legacy_dir

    return None


def list_skills(
    package: Optional[str] = None,
) -> dict[str, list[dict[str, str]]]:
    """List all skills across the ecosystem or for a specific package.

    Returns:
        Dict mapping package name -> list of skill info dicts.
        Each skill dict has: name, path, description (from frontmatter or first heading).
    """
    packages = discover_packages()

    if package:
        if package not in packages:
            return {}
        packages = {package: packages[package]}

    result: dict[str, list[dict[str, str]]] = {}

    for pkg_name, module_name in packages.items():
        skills_dir = _find_skills_dir(module_name, pkg_name)
        if skills_dir is None:
            continue

        skills = []

        # Main SKILL.md
        skill_md = skills_dir / "SKILL.md"
        if skill_md.exists():
            meta = _parse_frontmatter(skill_md)
            skills.append(
                {
                    "name": "SKILL",
                    "path": str(skill_md),
                    "description": meta.get("description", ""),
                }
            )

        # Reference pages
        refs_dir = skills_dir / "references"
        if refs_dir.is_dir():
            for md_file in sorted(refs_dir.glob("*.md")):
                meta = _parse_frontmatter(md_file)
                skills.append(
                    {
                        "name": md_file.stem,
                        "path": str(md_file),
                        "description": meta.get("description", ""),
                    }
                )

        # Legacy: flat .md files (not SKILL.md)
        if not (skills_dir / "SKILL.md").exists():
            for md_file in sorted(skills_dir.glob("*.md")):
                first_line = ""
                try:
                    first_line = md_file.read_text().split("\n", 1)[0].strip()
                    if first_line.startswith("#"):
                        first_line = first_line.lstrip("#").strip()
                except Exception:
                    pass
                skills.append(
                    {
                        "name": md_file.stem,
                        "path": str(md_file),
                        "description": first_line,
                    }
                )

        if skills:
            result[pkg_name] = skills

    return result


def get_skill(
    package: str,
    name: Optional[str] = None,
) -> Optional[str]:
    """Get the content of a skill file.

    Args:
        package: Package name (e.g. "scitex-stats")
        name: Reference name (e.g. "test-selection"). If None, returns SKILL.md.

    Returns:
        Skill content as string, or None if not found.
    """
    packages = discover_packages()
    module_name = packages.get(package)
    if module_name is None:
        return None

    skills_dir = _find_skills_dir(module_name, package)
    if skills_dir is None:
        return None

    if name is None:
        # Return main SKILL.md
        skill_file = skills_dir / "SKILL.md"
    else:
        # Try references/ first
        skill_file = skills_dir / "references" / f"{name}.md"
        if not skill_file.exists():
            # Try flat (legacy)
            skill_file = skills_dir / f"{name}.md"

    if not skill_file.exists():
        # Fuzzy match
        search_dirs = [skills_dir]
        refs_dir = skills_dir / "references"
        if refs_dir.is_dir():
            search_dirs.append(refs_dir)
        for d in search_dirs:
            candidates = list(d.glob(f"*{name}*"))
            if candidates:
                skill_file = candidates[0]
                break
        else:
            return None

    try:
        return skill_file.read_text()
    except Exception as e:
        logger.warning("Failed to read skill %s/%s: %s", package, name, e)
        return None


def get_skill_dir(package: str) -> Optional[Path]:
    """Get the skills directory path for a package.

    Returns:
        Path to skills directory, or None if not found.
    """
    packages = discover_packages()
    module_name = packages.get(package)
    if module_name is None:
        return None
    return _find_skills_dir(module_name, package)


def _parse_frontmatter(path: Path) -> dict[str, str]:
    """Parse YAML frontmatter from a markdown file.

    Returns dict with frontmatter keys, or empty dict if no frontmatter.
    """
    try:
        text = path.read_text()
    except Exception:
        return {}

    if not text.startswith("---"):
        return {}

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    result = {}
    for line in parts[1].strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result
