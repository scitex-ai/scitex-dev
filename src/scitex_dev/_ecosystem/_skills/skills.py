#!/usr/bin/env python3
"""Skills aggregation across the SciTeX ecosystem.

Each package places skills as markdown files inside its source tree::

    # New layout (preferred):
    src/<import_name>/_skills/<pip-name>/SKILL.md
    src/<import_name>/_skills/<pip-name>/sub-skill.md

    # Legacy layout (still supported):
    src/<import_name>/skills/SKILL.md
    src/<import_name>/skills/references/*.md

Export target (scitex namespace)::

    ~/.scitex/dev/skills/<pip-name>/SKILL.md
    ~/.scitex/dev/skills/<pip-name>/sub-skill.md

Usage::

    from scitex_dev.ecosystem import list_skills, get_skill, export_skills

    list_skills()
    list_skills(package="scitex-stats")
    get_skill(package="scitex-stats")
    get_skill(package="scitex-stats", name="test-selection")
    export_skills(Path.home() / ".claude/skills/scitex")
    export_skills(Path("skills"), source="pypi", clean=True)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import scitex_logging as slogging

from ..._core.discovery import get_package_root
from ..._core.names import normalize_distribution_name
from ...skill_registry import SkillRegistryError
from ._frontmatter import _parse_frontmatter
from ._frontmatter import _stamp_frontmatter_field as _stamp_frontmatter_field
from .installed_providers import (
    discover_skill_packages,
    enabled_skill_packages,
    get_skill_package_root,
)

logger = slogging.getLogger(__name__)


_DEFAULT_EXPORT_DIR_ENV = "SCITEX_DEV_SKILLS_DEFAULT_EXPORT_DIR"


def _get_default_export_dest() -> Path:
    """Get the default export destination from env or fallback."""
    env_val = os.environ.get(_DEFAULT_EXPORT_DIR_ENV)
    if env_val:
        return Path(env_val)
    return Path.home() / ".claude" / "skills" / "scitex"


def _find_skills_dir(
    module_name: str,
    pip_name: str,
    *,
    _root_fn=None,
) -> Optional[Path]:
    """Find the skills directory for a package.

    Resolution chain:
        1. New layout: <pkg_root>/_skills/<pip-name>/
        2. Legacy layout: <pkg_root>/skills/  (has SKILL.md)
        3. Legacy docs: <pkg_root>/docs/MASTER/skills/
    """
    root_lookup = _root_fn if _root_fn is not None else get_package_root
    root = root_lookup(module_name)
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


_SKIP_DIRS = {"__pycache__", "GITIGNORED", ".git"}


def _collect_skills_from_dir(
    skills_dir: Path,
    version: str,
) -> list[dict[str, str]]:
    """Collect skill entries recursively, preserving relative paths.

    Walks `skills_dir` recursively and records every `*.md` file. Each entry
    carries `rel_path` (relative to `skills_dir`), so the exporter can
    reproduce the directory structure under the destination.

    For the canonical `_skills/general/` use case this means the nested
    `03_interface/04_skills/00_index.md` etc. files survive the round-trip.
    Legacy flat layouts (top-level `*.md` only) keep working unchanged.
    """
    skills: list[dict[str, str]] = []
    for md_file in sorted(skills_dir.rglob("*.md")):
        # Skip hidden / generated subtrees.
        if any(
            part in _SKIP_DIRS or part.startswith(".")
            for part in md_file.relative_to(skills_dir).parts[:-1]
        ):
            continue
        rel = md_file.relative_to(skills_dir)
        rel_str = str(rel)
        # `name` keeps backward-compat semantics for top-level files; nested
        # files get their full relative path (without `.md`) as the name so
        # downstream `list_skills` / `get_skill` callers can still address them.
        if rel_str == "SKILL.md":
            name = "SKILL"
        elif "/" in rel_str:
            name = rel_str[:-3]  # strip trailing .md
        else:
            name = md_file.stem
        meta = _parse_frontmatter(md_file)
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
                "rel_path": rel_str,
                "description": desc,
                "version": version,
            }
        )
    return skills


def list_skills(
    package: Optional[str] = None,
    *,
    _discover_fn=None,
    _root_fn=None,
    _version_fn=None,
) -> dict[str, list[dict[str, str]]]:
    """List all skills across the ecosystem or for a specific package.

    Returns:
        Dict mapping skill namespace -> list of skill info dicts.
        Each entry carries its owning distribution plus name, path,
        rel_path, description and installed owner version. Disabled owners
        are excluded; ambiguous namespaces raise SkillRegistryError.
    """
    package = normalize_distribution_name(package) if package is not None else None
    discover = (
        _discover_fn
        if _discover_fn is not None
        else lambda: discover_skill_packages(package=package)
    )
    root_lookup = _root_fn if _root_fn is not None else get_package_root
    version_lookup = _version_fn if _version_fn is not None else _get_package_version

    packages = enabled_skill_packages(discover())

    if package:
        selected = {
            name
            for name in packages
            if package in (name, packages.owners.get(name, name))
        }
        if not selected:
            return {}
        selected_owners = {packages.owners[name] for name in selected}
        selected = {
            name for name in packages if packages.owners[name] in selected_owners
        }
    else:
        selected = set(packages)

    result: dict[str, list[dict[str, str]]] = {}

    def add_namespace(name, entries, owner):
        if name in result:
            previous = result[name][0]["owner"]
            raise SkillRegistryError(
                f"duplicate skill namespace {name!r}: {previous!r} and {owner!r}"
            )
        result[name] = [{**entry, "owner": owner} for entry in entries]

    for pkg_name, module_name in packages.items():
        if pkg_name not in selected:
            continue
        owner = packages.owners.get(pkg_name, pkg_name)
        root = (
            root_lookup(module_name)
            if _root_fn is not None
            else get_skill_package_root(owner, module_name)
        )
        provider_found = False
        # 1. Standard per-package skills
        skills_dir = _find_skills_dir(module_name, pkg_name, _root_fn=lambda _: root)
        if skills_dir is not None:
            version = version_lookup(owner)
            skills = _collect_skills_from_dir(skills_dir, version)
            if skills:
                add_namespace(pkg_name, skills, owner)
                provider_found = True

        # 2. Extra skill namespaces (e.g., _skills/general/ in scitex-python)
        if root is not None:
            extra_skills_root = root / "_skills"
            if extra_skills_root.is_dir():
                version = version_lookup(owner)
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
                            add_namespace(ns_name, extra, owner)
                            provider_found = True
        if not provider_found and _discover_fn is None:
            raise SkillRegistryError(
                f"registered skill provider {owner!r} has no skill resources in {root}"
            )

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
    package = normalize_distribution_name(package)
    packages = enabled_skill_packages(discover_skill_packages(package=package))
    module_name = packages.get(package)
    if module_name is None:
        return None

    root = get_skill_package_root(packages.owners.get(package, package), module_name)
    skills_dir = _find_skills_dir(module_name, package, _root_fn=lambda _: root)
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
    package = normalize_distribution_name(package)
    packages = enabled_skill_packages(discover_skill_packages(package=package))
    module_name = packages.get(package)
    if module_name is None:
        return None
    root = get_skill_package_root(packages.owners.get(package, package), module_name)
    return _find_skills_dir(module_name, package, _root_fn=lambda _: root)


def export_skills(
    dest: Path,
    *,
    package: str | None = None,
    clean: bool = False,
    source: str = "installed",
    link: bool = False,
    force_copy: bool = False,
    _discover_fn=None,
    _root_fn=None,
    _version_fn=None,
) -> dict[str, list[Path]]:
    """Install a hashed projection, preserving other packages and foreign files.

    Dirty/unmanaged destinations are refused; force_copy overrides link autodetection.
    """
    from ...skill_registry import SkillRegistryError
    from .transaction import install_projection

    finalized, exported = install_projection(
        dest,
        package=package,
        clean=clean,
        source=source,
        link=link,
        force_copy=force_copy,
        _discover_fn=_discover_fn,
        _root_fn=_root_fn,
        _version_fn=_version_fn,
    )
    if not finalized.audit.ok:
        details = "; ".join(
            f"{i.code}:{i.name}: {i.message}" for i in finalized.audit.issues
        )
        raise SkillRegistryError(f"skill install refused: {details}")
    return exported


def _export_skills_unchecked(*args, **kwargs):
    """Private stage-only materializer; public exports use the transaction."""
    from .legacy_export import export_unchecked

    return export_unchecked(*args, **kwargs)


def _generate_root_skill_md(dest: Path, exported: dict[str, list[Path]]) -> None:
    """Generate a categorized SKILL.md at the scitex/ root.

    Delegated to :mod:`_skills_categories` so the long category map and
    renderer live in their own module — keeps ``skills.py`` focused on
    discovery/export and within the project's per-file line budget.
    """
    from .skills_categories import render_root_skill_md

    render_root_skill_md(dest, exported)


# Re-export from refactored modules for backward compatibility
from .skills_drift import cached_skill_version, drift_warning, installed_version  # noqa: F401
from .skills_verify import verify_docs_and_skills  # noqa: F401
