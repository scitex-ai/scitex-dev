"""Skills-tree discovery — locate `<pkg>/_skills/<pip-name>/`.

Extracted from `_audit.py` (pure move, no behaviour change) to mirror the
sibling `_project/` auditor package layout and keep each module within
the repo file-size budget.
"""

from __future__ import annotations

from pathlib import Path


def _import_name(distribution: str) -> str:
    """Mirror `_cli_audit_api`: dist -> import name (`-` -> `_`)."""
    return distribution.replace("-", "_")


def _locate_skills_dir(distribution: str) -> Path | None:
    """Return `<pkg>/_skills/<pip-name>/` if it exists, else None.

    Resolution order (each step proceeds to the next on miss, so a package
    that is *neither* pip-installed *nor* registered still returns None and
    the caller can fire SK-101 confidently):

    1. **Installed package.** Import via ``importlib.util.find_spec``; walk
       each search location to ``_skills/<distribution>/`` and fall back
       to flat ``_skills/`` for legacy layouts.
    2. **On-disk source tree (registry fallback).** When the package is
       NOT installed in the auditor's venv (e.g. running ``audit-skills``
       against an ecosystem peer the developer has cloned locally but not
       ``pip install``-ed), look up ``distribution`` in
       ``scitex_dev._ecosystem._registry.ECOSYSTEM`` and probe
       ``<local_path>/src/<import_name>/_skills/<distribution>/`` (sub-skill
       layout) then ``<local_path>/src/<import_name>/_skills/`` (flat).

    Without step 2 every non-installed peer fires SK-101 even when its
    on-disk skill tree is perfectly valid — a phantom-violation class the
    journal kept tripping over (registry SK-* tallies on packages like
    ``scitex-events`` / ``scitex-etc`` were entirely install-availability
    artefacts of step 1, not real layout debt).

    Fallback to flat ``_skills/`` is preserved in both code paths so the
    caller can still distinguish SK-101 (no skills tree at all) from
    SK-102 (skills tree exists but missing the canonical sub-pip-name
    directory).
    """
    import importlib.util

    import_name = _import_name(distribution)

    # 1. Installed package.
    spec = importlib.util.find_spec(import_name)
    if spec is not None and spec.submodule_search_locations:
        for loc in spec.submodule_search_locations:
            candidate = Path(loc) / "_skills" / distribution
            if candidate.is_dir():
                return candidate
            flat = Path(loc) / "_skills"
            if flat.is_dir():
                return flat

    # 2. On-disk source tree via the ecosystem registry. Defensive — a
    # stale / partial registry import must never break the per-package
    # audit; fall through to None and let SK-101 fire as before.
    try:
        from ...._ecosystem._registry import ECOSYSTEM
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
    src_pkg = root / "src" / import_name
    candidate = src_pkg / "_skills" / distribution
    if candidate.is_dir():
        return candidate
    flat = src_pkg / "_skills"
    if flat.is_dir():
        return flat
    return None


def _locate_skills_dir_under(repo_root: Path, distribution: str) -> Path | None:
    """Return `<repo_root>/src/<import_name>/_skills/<dist>` (or flat), else None.

    The `--path`-honouring variant of :func:`_locate_skills_dir`: resolves
    the skills tree under an EXPLICIT repo root (e.g. a worktree / CI
    checkout passed via ``--path``) instead of the installed / registry
    location, so the same wrong-tree footgun `resolve_target_tree` closed
    for audit-project/django/python-apis is closed for audit-skills too.

    Both the sub-pip-name layout (``_skills/<distribution>/``) and the
    legacy flat layout (``_skills/``) are probed, mirroring the
    registry-fallback branch of :func:`_locate_skills_dir`, so the caller
    can still distinguish SK-101 from SK-102. Returns None when the repo
    ships no ``_skills/`` tree — the caller then fires SK-101 / skips as
    it would for any tree with no skills.
    """
    import_name = _import_name(distribution)
    src_pkg = repo_root / "src" / import_name
    candidate = src_pkg / "_skills" / distribution
    if candidate.is_dir():
        return candidate
    flat = src_pkg / "_skills"
    if flat.is_dir():
        return flat
    return None


__all__ = ["_import_name", "_locate_skills_dir", "_locate_skills_dir_under"]
