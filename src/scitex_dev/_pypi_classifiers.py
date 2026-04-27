#!/usr/bin/env python3
# Timestamp: 2026-04-27
# File: scitex_dev/_pypi_classifiers.py

"""Local validation of PyPI trove classifiers.

PyPI returns ``400 Bad Request`` on upload if any classifier is unknown,
which wastes a build cycle. This module validates classifiers in
``pyproject.toml`` *before* a build runs.

Real-world example: ``Topic :: Software Development :: Testing :: Benchmark``
is plausible-looking but **not** in the trove. Pre-validating turns the
PyPI 400 into a local fast-fail.
"""

from __future__ import annotations

import re
from pathlib import Path

_VALID_CLASSIFIERS_CACHE: set[str] | None = None


def _load_valid_classifiers() -> set[str]:
    """Return the set of valid PyPI trove classifiers.

    Uses the bundled ``trove-classifiers`` package when available. Returns
    an empty set on failure (caller should treat empty as "skip validation").
    """
    global _VALID_CLASSIFIERS_CACHE
    if _VALID_CLASSIFIERS_CACHE is not None:
        return _VALID_CLASSIFIERS_CACHE
    try:
        from trove_classifiers import classifiers as _all  # type: ignore

        _VALID_CLASSIFIERS_CACHE = set(_all)
    except ImportError:
        _VALID_CLASSIFIERS_CACHE = set()
    return _VALID_CLASSIFIERS_CACHE


def _extract_classifiers(pyproject_text: str) -> list[str]:
    """Extract the ``[project].classifiers`` list from pyproject.toml text.

    Light-touch: greps the ``classifiers = [ ... ]`` block. Doesn't handle
    every TOML edge case — just the common single-block form.
    """
    m = re.search(
        r"^classifiers\s*=\s*\[(.*?)\]",
        pyproject_text,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        return []
    return re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))


def validate_classifiers(package_dir: str | Path) -> list[str]:
    """Return invalid classifiers from ``pyproject.toml``.

    Empty list means all classifiers are valid (or validation was skipped
    because ``trove-classifiers`` isn't installed).
    """
    pyproject = Path(package_dir) / "pyproject.toml"
    if not pyproject.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject}")
    valid = _load_valid_classifiers()
    if not valid:
        return []
    declared = _extract_classifiers(pyproject.read_text(encoding="utf-8"))
    return [c for c in declared if c not in valid]


__all__ = ["validate_classifiers"]
