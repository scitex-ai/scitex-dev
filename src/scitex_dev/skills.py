#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skills aggregation across the SciTeX ecosystem.

Each package places skills as markdown files inside its source tree::

    # New layout (preferred):
    src/<import_name>/_skills/<pip-name>/SKILL.md
    src/<import_name>/_skills/<pip-name>/sub-skill.md

    # Legacy layout (still supported):
    src/<import_name>/skills/SKILL.md
    src/<import_name>/skills/references/*.md

Export target (scitex namespace)::

    .claude/skills/scitex/<pip-name>/SKILL.md
    .claude/skills/scitex/<pip-name>/sub-skill.md

Usage::

    from scitex_dev.skills import list_skills, get_skill, export_skills

    list_skills()
    list_skills(package="scitex-stats")
    get_skill(package="scitex-stats")
    get_skill(package="scitex-stats", name="test-selection")
    export_skills()                        # -> .claude/skills/scitex/
    export_skills(mode="upgrade")          # clean replacement
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from ._discovery import discover_packages, get_package_root

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "scitex_dev.skills"

_DEFAULT_EXPORT_DIR_ENV = "SCITEX_DEV_SKILLS_DEFAULT_EXPORT_DIR"


def _get_default_export_dest() -> Path:
    """Get the default export destination from env or fallback."""
    env_val = os.environ.get(_DEFAULT_EXPORT_DIR_ENV)
    if env_val:
        return Path(env_val)
    return Path(".claude") / "skills" / "scitex"


def _find_skills_dir(module_name: str, pip_name: str) -> Optional[Path]:
    """Find the skills directory for a package.

    Resolution chain:
        1. New layout: <pkg_root>/_skills/<pip-name>/
        2. Legacy layout: <pkg_root>/skills/  (has SKILL.md)
        3. Legacy docs: <pkg_root>/docs/MASTER/skills/
    """
    root = get_package_root(module_name)
    if root is None:
        return None

    # 1. New layout: _skills/<pip-name>/
    new_dir = root / "_skills" / pip_name
    if new_dir.is_dir() and (new_dir / "SKILL.md").exists():
        return new_dir

    # 2. DEPRECATED: skills/ (flat, no package-name subdir)
    legacy_dir = root / "skills"
    if legacy_dir.is_dir() and (legacy_dir / "SKILL.md").exists():
        logger.warning(
            "Package '%s' uses deprecated skills/ layout — "
            "migrate to _skills/%s/SKILL.md",
            pip_name,
            pip_name,
        )
        return legacy_dir

    # 3. DEPRECATED: docs/MASTER/skills/
    docs_dir = root / "docs" / "MASTER" / "skills"
    if docs_dir.is_dir():
        logger.warning(
            "Package '%s' uses deprecated docs/MASTER/skills/ layout — "
            "migrate to _skills/%s/SKILL.md",
            pip_name,
            pip_name,
        )
        return docs_dir

    return None


def _get_package_version(pip_name: str) -> str:
    """Get installed version for a package."""
    try:
        from importlib.metadata import version

        return version(pip_name)
    except Exception:
        return "unknown"


def _collect_skills_from_dir(
    skills_dir: Path,
    version: str,
) -> list[dict[str, str]]:
    """Collect skill entries from a single skills directory."""
    skills = []
    for md_file in sorted(skills_dir.glob("*.md")):
        meta = _parse_frontmatter(md_file)
        name = "SKILL" if md_file.name == "SKILL.md" else md_file.stem
        desc = meta.get("description", "")
        if not desc and md_file.name != "SKILL.md":
            try:
                first_line = md_file.read_text().split("\n", 1)[0].strip()
                if first_line.startswith("#"):
                    desc = first_line.lstrip("#").strip()
            except Exception:
                pass
        skills.append(
            {
                "name": name,
                "path": str(md_file),
                "description": desc,
                "version": version,
            }
        )

    # DEPRECATED: also check references/ subdir
    refs_dir = skills_dir / "references"
    if refs_dir.is_dir():
        for md_file in sorted(refs_dir.glob("*.md")):
            meta = _parse_frontmatter(md_file)
            skills.append(
                {
                    "name": md_file.stem,
                    "path": str(md_file),
                    "description": meta.get("description", ""),
                    "version": version,
                }
            )
    return skills


def list_skills(
    package: Optional[str] = None,
) -> dict[str, list[dict[str, str]]]:
    """List all skills across the ecosystem or for a specific package.

    Returns:
        Dict mapping package name -> list of skill info dicts.
        Each dict has: name, path, description, version.
    """
    packages = discover_packages()

    if package:
        if package not in packages:
            return {}
        packages = {package: packages[package]}

    result: dict[str, list[dict[str, str]]] = {}

    for pkg_name, module_name in packages.items():
        # 1. Standard per-package skills
        skills_dir = _find_skills_dir(module_name, pkg_name)
        if skills_dir is not None:
            version = _get_package_version(pkg_name)
            skills = _collect_skills_from_dir(skills_dir, version)
            if skills:
                result[pkg_name] = skills

        # 2. Extra skill namespaces (e.g., _skills/general/ in scitex-python)
        root = get_package_root(module_name)
        if root is not None:
            extra_skills_root = root / "_skills"
            if extra_skills_root.is_dir():
                version = _get_package_version(pkg_name)
                for sub_dir in sorted(extra_skills_root.iterdir()):
                    if not sub_dir.is_dir():
                        continue
                    ns_name = sub_dir.name
                    # Skip the package's own name (already handled above)
                    if ns_name == pkg_name:
                        continue
                    if (sub_dir / "SKILL.md").exists():
                        extra = _collect_skills_from_dir(sub_dir, version)
                        if extra:
                            result[ns_name] = extra
            result[pkg_name] = skills

    return result


def get_skill(
    package: str,
    name: Optional[str] = None,
) -> Optional[str]:
    """Get the content of a skill file.

    Args:
        package: Package name (e.g. "scitex-stats")
        name: Skill name (e.g. "test-selection"). If None, returns SKILL.md.

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
        skill_file = skills_dir / "SKILL.md"
    else:
        # Flat lookup first (new layout)
        skill_file = skills_dir / f"{name}.md"
        if not skill_file.exists():
            # Legacy: references/ subdir
            skill_file = skills_dir / "references" / f"{name}.md"

    if not skill_file.exists():
        # Fuzzy match across all locations
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
    """Get the skills directory path for a package."""
    packages = discover_packages()
    module_name = packages.get(package)
    if module_name is None:
        return None
    return _find_skills_dir(module_name, package)


def export_skills(
    dest: Optional[Path] = None,
    package: Optional[str] = None,
    mode: str = "export",
) -> dict[str, list[Path]]:
    """Export skills to a directory under scitex namespace.

    Target layout::
        <dest>/scitex/<pkg-name>/SKILL.md
        <dest>/scitex/<pkg-name>/sub-skill.md

    Args:
        dest: Target directory. Default from SCITEX_DEV_SKILLS_DEFAULT_EXPORT_DIR
              env var, or ``.claude/skills/scitex``.
        package: Export only this package. None exports all.
        mode: "export" (default, copy new/changed), "update" (rsync-like,
              preserve local changes), or "upgrade" (clean replacement).

    Returns:
        Dict mapping package name -> list of exported file paths.
    """
    if dest is None:
        dest = _get_default_export_dest()
    else:
        # Ensure scitex namespace even with custom --dest
        if dest.name != "scitex":
            dest = dest / "scitex"

    if mode == "upgrade" and dest.is_dir():
        # Clean the target packages (not the whole dest)
        all_skills = list_skills(package=package)
        for pkg_name in all_skills:
            pkg_dir = dest / pkg_name
            if pkg_dir.is_dir():
                shutil.rmtree(pkg_dir)

    all_skills = list_skills(package=package)
    exported: dict[str, list[Path]] = {}

    for pkg_name, entries in all_skills.items():
        pkg_dest = dest / pkg_name
        pkg_dest.mkdir(parents=True, exist_ok=True)

        pkg_files: list[Path] = []
        for entry in entries:
            src_path = Path(entry["path"])
            if not src_path.exists():
                continue

            # Flat output: all files directly in pkg_dest (no references/ subdir)
            name = entry["name"]
            out_file = pkg_dest / ("SKILL.md" if name == "SKILL" else f"{name}.md")

            if mode == "update" and out_file.exists():
                # Only overwrite if source is newer
                if src_path.stat().st_mtime <= out_file.stat().st_mtime:
                    pkg_files.append(out_file)
                    continue

            # Copy and flatten references/ paths in content
            content = src_path.read_text(encoding="utf-8")
            if name == "SKILL" and "references/" in content:
                import re

                content = re.sub(r"references/", "", content)
            out_file.write_text(content, encoding="utf-8")
            pkg_files.append(out_file)

        if pkg_files:
            exported[pkg_name] = pkg_files

    # Generate root SKILL.md index for scitex/ directory
    _generate_root_skill_md(dest, exported)

    return exported


def _generate_root_skill_md(dest: Path, exported: dict[str, list[Path]]) -> None:
    """Generate a SKILL.md at the scitex/ root that indexes all sub-packages."""
    if not exported:
        return

    lines = [
        "---",
        "name: scitex",
        "description: SciTeX ecosystem skills — general standards, package-specific guides, and workflow references. Use when working on any SciTeX package.",
        "user-invocable: false",
        "---",
        "",
        "# SciTeX Ecosystem Skills",
        "",
    ]

    # Group: general first, then packages alphabetically
    if "general" in exported:
        lines.append("## General Standards")
        lines.append(
            "- For ecosystem-wide standards, see [general/SKILL.md](general/SKILL.md)"
        )
        lines.append("")

    pkg_names = sorted(k for k in exported if k != "general")
    if pkg_names:
        lines.append("## Package Skills")
        for pkg in pkg_names:
            lines.append(f"- [{pkg}]({pkg}/SKILL.md)")
        lines.append("")

    skill_md = dest / "SKILL.md"
    skill_md.write_text("\n".join(lines))


def _parse_frontmatter(path: Path) -> dict[str, str]:
    """Parse YAML frontmatter from a markdown file."""
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
