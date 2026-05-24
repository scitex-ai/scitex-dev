"""§6 — Python-API ↔ MCP-tool parity check (extracted from `_mcp_audit`).

Two concerns live here:

1. **Parity / orphan-tool detection** (`_check_api_parity`) — every MCP
   tool should map to a public Python-API function and vice-versa. A
   large mismatch in either direction is flagged §6.

2. **Per-package exemption** (`is_mcp_parity_exempt`) — some packages
   legitimately expose far more MCP tools than Python-API functions.
   figrecipe mirrors ~74 matplotlib Axes methods (plot / scatter / bar /
   hist / …) as tools that have no standalone Python-function counterpart
   by design; for that package class §6 is a false positive.

A package declares the exemption in its OWN repo, mirroring the
``no_cli`` / ``no_e2e`` opt-out precedent in
``_check_smoke_e2e_layers.py``::

    # pyproject.toml (REQUIRED primary)
    [tool.scitex_dev]
    mcp_parity_exempt = true

    # .scitex/dev/config.yaml (OPTIONAL — convention parity)
    audit:
      mcp-parity-exempt: true

When set, `_check_api_parity` emits an informational "exempt by config"
line instead of a §6 violation. The rule still fires for every package
that did NOT declare the exemption.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from ._audit import Violation
from ._mcp_names import _import_name, _short_name


# --------------------------------------------------------------------- #
# §6 exemption — per-package opt-out                                    #
# --------------------------------------------------------------------- #

_TOOL_BLOCK_RE = re.compile(
    r"^\[tool\.scitex[_-]dev\](.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
_MCP_PARITY_EXEMPT_RE = re.compile(
    r"^\s*mcp_parity_exempt\s*=\s*true\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_YAML_MCP_PARITY_EXEMPT_RE = re.compile(
    r"^\s*mcp-parity-exempt\s*:\s*true\s*$",
    re.MULTILINE | re.IGNORECASE,
)


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
    return None


def _audited_repo_root(package: str) -> Path | None:
    """Best-effort local checkout path for `package`.

    Prefers the ecosystem registry's ``local_path`` (the dev workstation
    case), then falls back to the installed/checked-out tree via
    ``find_spec``. The fallback is what makes the §6 exemption work in CI,
    where the registry path is absent but the package is editable-installed
    from the checkout.
    """
    try:
        from ...._ecosystem import get_local_path
    except ImportError:
        get_local_path = None  # type: ignore[assignment]

    if get_local_path is not None:
        try:
            path = get_local_path(package)
        except Exception:
            path = None
        if path is not None and path.is_dir():
            return path

    return _repo_root_from_import(package)


def is_mcp_parity_exempt(package: str, repo: Path | None = None) -> bool:
    """Return True when `package` declares §6 (MCP-parity) exemption.

    pyproject.toml ``[tool.scitex_dev] mcp_parity_exempt = true`` is the
    required primary; ``.scitex/dev/config.yaml`` ``audit.mcp-parity-exempt:
    true`` is honored for convention parity. Either form opts the package
    out of the §6 parity/orphan-tool check.

    Parameters
    ----------
    package
        ECOSYSTEM key (e.g. ``"figrecipe"``). Used to resolve the local
        checkout via the registry when `repo` is not given.
    repo
        Explicit repo root. When provided, the registry lookup is
        bypassed — used by tests that operate on a synthetic package
        tree.
    """
    root = repo if repo is not None else _audited_repo_root(package)
    if root is None:
        return False

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            txt = pyproject.read_text(errors="ignore")
        except OSError:
            txt = ""
        m = _TOOL_BLOCK_RE.search(txt)
        if m is not None and _MCP_PARITY_EXEMPT_RE.search(m.group(1)):
            return True

    cfg = root / ".scitex" / "dev" / "config.yaml"
    if cfg.is_file():
        try:
            cfg_txt = cfg.read_text(errors="ignore")
        except OSError:
            cfg_txt = ""
        if _YAML_MCP_PARITY_EXEMPT_RE.search(cfg_txt):
            return True

    return False


# --------------------------------------------------------------------- #
# §6 — Python API parity                                                 #
# --------------------------------------------------------------------- #


def _python_api_names(package: str) -> set[str]:
    """Return the set of public *function* names exported by `scitex_<pkg>`.

    Best-effort: imports the top-level module, reads `__all__` (or non-private
    attributes), and keeps only callables that are NOT classes/types. Classes
    are exposed as API but are rarely wrapped as MCP tools — including them
    in the parity check produces false positives.

    Two layouts are accepted, matching the two patterns in the
    SciTeX ecosystem:

    1. **Flat** — `pkg.<verb>_<noun>(...)` (the original convention).
       Used by scitex-stats, scitex-io, etc.
    2. **Nested** — `pkg.<noun>.<verb>(...)` (the CLI-mirror form).
       Each noun submodule re-exports verbs under their bare names;
       this auditor flattens them to `<noun>_<verb>` for the parity
       comparison so the MCP tool naming convention still applies
       (a tool named ``agent_list`` matches either ``pkg.agent_list``
       or ``pkg.agent.list``).
    """
    import inspect as _inspect

    import_name = _import_name(package)
    try:
        mod = importlib.import_module(import_name)
    except Exception:
        return set()
    names = getattr(mod, "__all__", None)
    if names is None:
        names = [n for n in dir(mod) if not n.startswith("_")]
    out: set[str] = set()
    for n in names:
        if not isinstance(n, str):
            continue
        val = getattr(mod, n, None)
        if val is None or _inspect.isclass(val):
            continue
        if _inspect.ismodule(val):
            # Nested-form noun submodule. Walk its public verbs and
            # surface them as `<noun>_<verb>` so the parity check can
            # match an MCP tool named the same way. Skip submodules
            # without an explicit __all__ — those tend to be deep
            # internals, not the package's CLI-tree mirror.
            sub_names = getattr(val, "__all__", None)
            if sub_names is None:
                continue
            for sub_n in sub_names:
                if not isinstance(sub_n, str):
                    continue
                sub_val = getattr(val, sub_n, None)
                if (
                    sub_val is None
                    or _inspect.isclass(sub_val)
                    or _inspect.ismodule(sub_val)
                    or not callable(sub_val)
                ):
                    continue
                # Trailing underscore is the Python idiom for keyword
                # aliasing (`import_`, `class_`); strip before joining
                # so `pkg.db.import_` matches MCP `db_import`.
                clean_verb = sub_n.rstrip("_")
                out.add(f"{n}_{clean_verb}")
            continue
        if callable(val):
            out.add(n)
    return out


def _check_api_parity(
    package: str,
    tool_names: set[str],
    out: list[Violation],
    repo: Path | None = None,
) -> None:
    """§6 — every Python API should map to an MCP tool (and vice versa).

    Skipped when the package declares `[tool.scitex_dev] mcp_parity_exempt
    = true` in its own pyproject.toml (see `is_mcp_parity_exempt`). Used by
    plotting/diagram-rich packages (e.g. figrecipe) whose MCP tools mirror
    matplotlib Axes methods with no standalone Python-function counterpart.

    `repo` overrides the registry path lookup for the exemption check —
    used by tests that operate on a synthetic package tree.
    """
    if is_mcp_parity_exempt(package, repo=repo):
        from .._emit import emit as _emit

        _emit(
            "info",
            f"{package}: §6 MCP-parity exempt by config "
            "([tool.scitex_dev] mcp_parity_exempt = true) — plotting/diagram-rich "
            "tool surface mirrors external methods with no Python-API counterpart",
        )
        return

    py_apis = _python_api_names(package)
    if not py_apis:
        return  # cannot establish parity; not the auditor's place to invent it.

    short = _short_name(package)
    # Normalize MCP names to compare against bare Python names.
    mcp_normalized = {n.removeprefix(f"{short}_") for n in tool_names}
    out.extend(_parity_violations(package, py_apis, mcp_normalized))


def _parity_violations(
    package: str, py_apis: set[str], mcp_normalized: set[str]
) -> list[Violation]:
    """Pure §6 comparison: given Python-API names and normalized MCP tool
    names, return the §6 violations (missing-in-MCP and orphan-tool).

    Split out from `_check_api_parity` so the comparison logic is testable
    with real sets — no module-import or registry I/O required.
    """
    out: list[Violation] = []

    missing_in_mcp = py_apis - mcp_normalized
    if missing_in_mcp and len(missing_in_mcp) > len(py_apis) * 0.5:
        out.append(
            Violation(
                package,
                "§6",
                f"{len(missing_in_mcp)}/{len(py_apis)} Python APIs have no "
                f"matching MCP tool (sample: {sorted(missing_in_mcp)[:3]})",
            )
        )

    # Orphan check (warn-tier; small set is normal for envelope tools).
    orphans = mcp_normalized - py_apis
    skill_tools = {"skills_list", "skills_get"}
    interesting_orphans = orphans - skill_tools
    if interesting_orphans and len(interesting_orphans) > 3:
        out.append(
            Violation(
                package,
                "§6",
                f"{len(interesting_orphans)} MCP tools have no matching Python API "
                f"(sample: {sorted(interesting_orphans)[:3]})",
            )
        )
    return out


__all__ = [
    "is_mcp_parity_exempt",
    "_parity_violations",
    "_python_api_names",
    "_check_api_parity",
]
