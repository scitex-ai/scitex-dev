"""Repo-root resolution for §6 exemption/allowlist reads (from `_mcp_parity`).

Answers ONE question for the §6 parity machinery: *which on-disk tree do
we read ``mcp_parity_exempt`` / ``mcp_tools_allowlist`` /
``.scitex/dev/config.yaml`` from?* Extracted from ``_mcp_parity`` (line
budget) together with the resolution-order fix described on
:func:`_audited_repo_root`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ._mcp_names import _import_name

__all__ = ["_audited_repo_root", "_repo_root_from_import"]


def _repo_root_from_import(package: str) -> Path | None:
    """Resolve the package's repo root from the installed/checked-out tree.

    Walks up from the import location (``src/<pkg>/__init__.py``) to the
    repo root that holds ``pyproject.toml``. Mirrors audit-project's
    ``_resolve_repo_root`` so the §6 exemption can be read from the tree
    that is actually being audited — critical in CI, where the editable
    install lives at ``$GITHUB_WORKSPACE`` and the ecosystem registry's
    fixed ``local_path`` does not exist on the runner.
    """
    import importlib.util

    import_name = _import_name(package)
    try:
        spec = importlib.util.find_spec(import_name)
    except (ImportError, ValueError, ModuleNotFoundError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    for loc in spec.submodule_search_locations:
        # src/<pkg>/__init__.py → repo root is two levels up (src layout)
        candidate = Path(loc).parent.parent
        if (candidate / "pyproject.toml").is_file():
            return candidate
        # flat layout fallback
        candidate = Path(loc).parent
        if (candidate / "pyproject.toml").is_file():
            return candidate

    # Fallback: module is in site-packages (non-editable PyPI install), so
    # walking up from its location won't find pyproject.toml. Try common
    # development checkout locations: $HOME/proj/<package>/ (which matches
    # the ecosystem registry's ~/proj/<name> convention) and all
    # /home/*/proj/<package>/ for container/multi-user environments.
    proj_roots: list[Path] = []
    try:
        home_proj = Path.home() / "proj"
        if home_proj.is_dir():
            proj_roots.append(home_proj)
    except Exception:
        pass
    try:
        for home_dir in Path("/home").iterdir():
            p = home_dir / "proj"
            if p.is_dir() and p not in proj_roots:
                proj_roots.append(p)
    except Exception:
        pass
    for root in proj_roots:
        candidate = root / package
        if (candidate / "pyproject.toml").is_file():
            return candidate.resolve()

    return None


def _registry_local_path(package: str) -> Path | None:
    """The ecosystem registry's ``local_path`` for `package`, if it exists."""
    try:
        from ...._ecosystem import get_local_path
    except ImportError:
        return None
    try:
        path = get_local_path(package)
    except Exception:
        return None
    if path is not None and path.is_dir():
        return path
    return None


def _audited_repo_root(
    package: str,
    registry_resolver: Callable[[str], Path | None] = _registry_local_path,
) -> Path | None:
    """Best-effort local checkout path for `package`.

    Prefers the tree that is ACTUALLY being audited — the
    installed/checked-out tree resolved via ``find_spec`` — and only then
    falls back to the ecosystem registry's ``local_path``. The order
    matters on SELF-HOSTED CI runners: the runner's home often carries a
    ``~/proj/<pkg>`` checkout (the registry convention), and preferring it
    would read §6 exemptions (``mcp_parity_exempt`` /
    ``mcp_tools_allowlist``) from that STALE tree instead of the PR
    checkout under audit — a PR declaring the exemption could never turn
    its own CI green (scitex-orochi #460, 2026-07-22). For editable
    installs (dev workstation AND CI) the import walk lands on the same
    checkout the registry would have named; the registry path only
    decides for non-editable site-packages installs, where no audited
    tree exists next to the import location.

    ``registry_resolver`` is injectable for tests (real default:
    :func:`_registry_local_path`).
    """
    root = _repo_root_from_import(package)
    if root is not None:
        return root
    return registry_resolver(package)
