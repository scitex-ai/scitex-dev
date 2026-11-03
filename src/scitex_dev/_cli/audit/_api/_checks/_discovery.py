"""Package-resolution helpers for the Python API auditor.

A resolved source checkout is authoritative. Installed-package discovery and
registry fallback apply only when the caller has not resolved a checkout.
Re-exported from ``_audit`` for existing imports.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _import_name(distribution: str) -> str:
    """`scitex-io` → `scitex_io` (canonical SciTeX convention)."""
    return distribution.replace("-", "_")


def _locate_init(
    distribution: str, import_name: str, *, repo_root: Path | None = None
) -> Path | None:
    """Locate ``<pkg>/__init__.py`` for the given distribution.

    With ``repo_root``, inspect only that checkout's src or flat package
    layout. A missing source initializer returns None; the auditor reports
    that the requested source cannot be audited rather than substituting an
    installed package. No consumer module is imported in this branch.

    Without a resolved checkout, try installed metadata first and then the
    ecosystem registry's source tree. Return None when neither is available.
    """
    # An already resolved checkout is authoritative. Never silently replace a
    # requested worktree with an installed copy or a registry checkout.
    if repo_root is not None:
        root = Path(repo_root)
        for candidate in (
            root / "src" / import_name / "__init__.py",
            root / import_name / "__init__.py",
        ):
            if candidate.is_file():
                return candidate
        return None

    # 1. Installed package (only when no checkout was resolved).
    spec = importlib.util.find_spec(import_name)
    if spec is not None and spec.origin is not None:
        origin = Path(spec.origin)
        if origin.name == "__init__.py":
            return origin

    # 2. On-disk source tree via the ecosystem registry. Defensive — a
    # stale / partial registry import must never break the per-package
    # audit; fall through to None and let the caller skip cleanly.
    try:
        from ....._ecosystem._registry import ECOSYSTEM
    except Exception:  # pragma: no cover — defensive
        return None
    info = ECOSYSTEM.get(distribution) or {}
    local_path = info.get("local_path")
    if not local_path:
        return None
    try:
        root = Path(local_path).expanduser()
    except (RuntimeError, OSError):  # pragma: no cover — defensive
        return None
    if not root.is_dir():
        return None
    candidate = root / "src" / import_name / "__init__.py"
    if candidate.is_file():
        return candidate
    return None


__all__ = ["_import_name", "_locate_init"]
