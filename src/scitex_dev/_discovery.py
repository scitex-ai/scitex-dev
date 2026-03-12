#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Discover scitex ecosystem packages that expose docs via entry points.

Each package registers itself in pyproject.toml:
    [project.entry-points."scitex_dev.docs"]
    scitex-writer = "scitex_writer"

This module lazily discovers all registered packages and caches the result.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "scitex_dev.docs"

# Cache: populated on first call, cleared by invalidate_cache()
_cache: Optional[dict[str, str]] = None


def discover_packages() -> dict[str, str]:
    """Discover all installed packages with scitex_dev.docs entry points.

    Returns:
        Dict mapping package name → Python module name.
        e.g. {"scitex-writer": "scitex_writer", "figrecipe": "figrecipe"}
    """
    global _cache
    if _cache is not None:
        return _cache

    packages = {}
    try:
        from importlib.metadata import entry_points

        # Python 3.12+ returns SelectableGroups; 3.9+ needs group= kwarg
        eps = entry_points(group=_ENTRY_POINT_GROUP)
        for ep in eps:
            packages[ep.name] = ep.value
    except Exception:
        logger.debug("Failed to discover entry points for %s", _ENTRY_POINT_GROUP)

    _cache = packages
    return packages


def invalidate_cache() -> None:
    """Clear the discovery cache. Useful after installing new packages."""
    global _cache
    _cache = None


def get_package_root(module_name: str) -> Optional[Path]:
    """Get the installed root directory of a Python package.

    Args:
        module_name: Python import name (e.g. "scitex_writer")

    Returns:
        Path to the package directory, or None if not importable.
    """
    try:
        mod = importlib.import_module(module_name)
        if hasattr(mod, "__path__"):
            return Path(mod.__path__[0])
        elif hasattr(mod, "__file__") and mod.__file__:
            return Path(mod.__file__).parent
    except ImportError:
        pass
    return None


def get_sphinx_source(module_name: str) -> Optional[Path]:
    """Find the Sphinx source directory for a package (dev environment only).

    Looks for docs/sphinx/conf.py relative to the package's repo root.
    """
    pkg_root = get_package_root(module_name)
    if pkg_root is None:
        return None

    # Walk up to find repo root (has pyproject.toml or .git)
    candidate = pkg_root
    for _ in range(5):
        candidate = candidate.parent
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            sphinx_dir = candidate / "docs" / "sphinx"
            if (sphinx_dir / "conf.py").exists():
                return sphinx_dir
            break
    return None
