#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skills aggregation across the SciTeX ecosystem.

Each package places skills as markdown files in docs/MASTER/skills/.
This module discovers and aggregates them via the same entry point
system used by docs discovery.

Usage:
    from scitex_dev.skills import list_skills, get_skill

    # List all skills across ecosystem
    list_skills()

    # List skills for a specific package
    list_skills(package="figrecipe")

    # Get a specific skill content
    get_skill(package="figrecipe", name="01-package-architecture")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ._discovery import discover_packages, get_package_root

logger = logging.getLogger(__name__)


def _find_skills_dir(module_name: str) -> Optional[Path]:
    """Find docs/MASTER/skills/ directory for a package."""
    root = get_package_root(module_name)
    if root is None:
        return None
    skills_dir = root / "docs" / "MASTER" / "skills"
    if skills_dir.is_dir():
        return skills_dir
    return None


def list_skills(
    package: Optional[str] = None,
) -> dict[str, list[dict[str, str]]]:
    """List all skills across the ecosystem or for a specific package.

    Returns:
        Dict mapping package name → list of skill info dicts.
        Each skill dict has: name, path, description (first line).
    """
    packages = discover_packages()

    if package:
        if package not in packages:
            return {}
        packages = {package: packages[package]}

    result: dict[str, list[dict[str, str]]] = {}

    for pkg_name, module_name in packages.items():
        skills_dir = _find_skills_dir(module_name)
        if skills_dir is None:
            continue

        skills = []
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
    name: str,
) -> Optional[str]:
    """Get the content of a specific skill file.

    Args:
        package: Package name (e.g. "figrecipe")
        name: Skill name without .md extension (e.g. "01-package-architecture")

    Returns:
        Skill content as string, or None if not found.
    """
    packages = discover_packages()
    module_name = packages.get(package)
    if module_name is None:
        return None

    skills_dir = _find_skills_dir(module_name)
    if skills_dir is None:
        return None

    skill_file = skills_dir / f"{name}.md"
    if not skill_file.exists():
        # Try without extension match
        candidates = list(skills_dir.glob(f"*{name}*"))
        if candidates:
            skill_file = candidates[0]
        else:
            return None

    try:
        return skill_file.read_text()
    except Exception as e:
        logger.warning("Failed to read skill %s/%s: %s", package, name, e)
        return None
