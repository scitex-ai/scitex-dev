#!/usr/bin/env python3
# Timestamp: 2026-04-28
# File: scitex_dev/_version_fixer.py

"""Eliminate ``__version__`` literal drift by switching to importlib.metadata.

The 2026-04-28 audit pass surfaced 30 packages where ``__init__.py`` had a
stale ``__version__ = "X.Y.Z"`` literal that didn't match pyproject. Each
release bump silently created new drift unless the developer remembered
to update both files.

Solution: replace the literal with a ``importlib.metadata.version(<dist>)``
lookup with a fallback for editable / detached installs. Once a package
uses this pattern, ``__version__`` is sourced from the installed
distribution metadata at import time, so it can never drift.

This module performs that rewrite idempotently. It detects the existing
literal, replaces it with the canonical block, and leaves files already
using importlib.metadata alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Canonical block. Wrapped in try/except so that:
# - editable installs without a wheel still get a sane fallback
# - the import works on Python 3.8+ even though importlib.metadata
#   semantics differ (importlib.metadata.PackageNotFoundError → 3.8+)
CANONICAL_BLOCK = """try:
    from importlib.metadata import version as _v, PackageNotFoundError
    try:
        __version__ = _v("{dist}")
    except PackageNotFoundError:
        __version__ = "0.0.0+local"
    del _v, PackageNotFoundError
except ImportError:  # pragma: no cover — only on ancient Pythons
    __version__ = "0.0.0+local"
"""


@dataclass
class FixResult:
    repo: Path
    package: str
    init_py: Path
    action: str  # "rewrote" | "already_dynamic" | "no_literal" | "no_init"
    old_value: str | None = None
    failed_reason: str | None = None


@dataclass
class BulkResult:
    fixes: list[FixResult] = field(default_factory=list)

    @property
    def rewrote(self) -> list[FixResult]:
        return [f for f in self.fixes if f.action == "rewrote"]


def _read_pyproject_name(pyproject: Path) -> str | None:
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None


def fix_version(repo: Path, dry_run: bool = False) -> FixResult:
    """Rewrite ``src/<imp>/__init__.py`` to source ``__version__`` dynamically."""
    pyproject = repo / "pyproject.toml"
    pkg = _read_pyproject_name(pyproject) or repo.name
    imp = pkg.replace("-", "_")
    init_py = repo / "src" / imp / "__init__.py"

    if not init_py.is_file():
        return FixResult(repo=repo, package=pkg, init_py=init_py, action="no_init")

    try:
        text = init_py.read_text(encoding="utf-8")
    except OSError as exc:
        return FixResult(
            repo=repo,
            package=pkg,
            init_py=init_py,
            action="no_init",
            failed_reason=str(exc),
        )

    # Already-dynamic detection: importlib.metadata import + a __version__
    # assigned from a callable. Common patterns:
    #   __version__ = version("demo")
    #   __version__ = _v("demo")
    #   __version__ = importlib.metadata.version("demo")
    if "importlib.metadata" in text and re.search(
        r"__version__\s*=\s*(?:[\w.]+\.)?(?:version|_v)\s*\(",
        text,
    ):
        return FixResult(
            repo=repo,
            package=pkg,
            init_py=init_py,
            action="already_dynamic",
        )

    # Find a top-level `__version__ = "..."` literal.
    pattern = re.compile(r'^__version__\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return FixResult(
            repo=repo,
            package=pkg,
            init_py=init_py,
            action="no_literal",
        )

    block = CANONICAL_BLOCK.format(dist=pkg)
    # Replace the single line with the canonical block.
    new_text = text[: m.start()] + block.rstrip() + text[m.end() :]
    if not dry_run:
        init_py.write_text(new_text)
    return FixResult(
        repo=repo,
        package=pkg,
        init_py=init_py,
        action="rewrote",
        old_value=m.group(1),
    )


def fix_versions_bulk(repos: list[Path], dry_run: bool = False) -> BulkResult:
    """Apply fix_version across many repos."""
    out = BulkResult()
    for repo in repos:
        out.fixes.append(fix_version(repo, dry_run=dry_run))
    return out


__all__ = [
    "CANONICAL_BLOCK",
    "FixResult",
    "BulkResult",
    "fix_version",
    "fix_versions_bulk",
]
