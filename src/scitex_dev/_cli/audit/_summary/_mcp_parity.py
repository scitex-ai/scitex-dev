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

3. **Ratchet** (`record_parity_baseline` + `_mcp_parity_baseline`) — a
   package that DOES owe the parity but cannot close the gap at once
   commits `.scitex/dev/mcp-parity-baseline.yaml`; new gaps then fail and
   the recorded backlog may only shrink.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import get_origin

from ._audit import Violation
from ._mcp_names import _import_name, _short_name
from ._mcp_parity_baseline import (
    MalformedParityBaseline,
    format_backlog_notice,
    load_parity_baseline,
    write_parity_baseline,
)

# Pure name comparison lives in `_mcp_parity_match` (line budget);
# re-exported so existing importers keep their paths.
from ._mcp_parity_match import (
    _parity_violations,
    _tool_matches_api,
    missing_python_apis,
)

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


# Repo-root resolution (which tree do we read exemptions from?) lives in
# `_mcp_repo_root` — audited tree first, registry local_path fallback.
# Re-imported here so existing importers/tests keep their paths.
from ._mcp_repo_root import (
    _audited_repo_root,
    _repo_root_from_import,  # noqa: F401  -- re-export for existing importers
)


def is_mcp_parity_exempt(package: str, repo: Path | None) -> bool:
    """Return True when `package` declares §6 (MCP-parity) exemption.

    pyproject.toml ``[tool.scitex_dev] mcp_parity_exempt = true`` is the
    required primary; ``.scitex/dev/config.yaml`` ``audit.mcp-parity-exempt:
    true`` is honored for convention parity. Either form opts the package
    out of the §6 parity/orphan-tool check.

    ``repo`` HAS NO DEFAULT, and neither do the two readers below
    ---------------------------------------------------------------
    All four exemption readers in this package share one resolver and one
    hazard. §6a was broken for exactly one reason — a caller forgot this
    argument — and got a silent fallback to a DIFFERENT TREE than the one
    being audited, whose only symptom was an exemption that would not take
    effect. Measured 2026-08-20: three sites passed it, one did not, and
    every one of the four already used ``_audited_repo_root``. So the
    invariant worth enforcing is not "use the resolver" — that was already
    true where the bug was, and therefore caught nothing — but "be CALLED
    WITH the audited tree". A required parameter is that invariant enforced
    by the language rather than remembered.

    These three were correct when §6a was fixed. They are required anyway:
    what made §6a break was that forgetting was POSSIBLE, and removing that
    from three of four functions leaves it to resurface at the fourth.

    Parameters
    ----------
    package
        ECOSYSTEM key (e.g. ``"figrecipe"``). Used to resolve the local
        checkout via the registry when `repo` is None.
    repo
        The audited repo root. Passing ``None`` explicitly still selects
        discovery, and means "I have no audited tree" — a decision made
        visibly, rather than a default nobody chose.
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


def declares_no_mcp(package: str, repo: Path | None) -> bool:
    """Return True when `package` declares the ``no-mcp`` CAPABILITY.

    Reads ``.scitex/dev/config.yaml`` ``audit.capabilities: [no-mcp]`` via the
    shared :func:`load_config` loader (operator directive 2026-06-22). This is
    the package-TYPE knob for ALIAS packages with no first-party MCP surface
    (e.g. ``scitex-plt`` aliases ``figrecipe``): the §6 MCP↔Python-API parity
    check does not apply, and the auditor skips it with a VISIBLE notice.

    Distinct from :func:`is_mcp_parity_exempt` (the older ``mcp_parity_exempt``
    flag for diagram-rich packages whose tools mirror external methods): both
    skip §6, but the capability emits the canonical
    ``skipped (declared capability: no-mcp)`` notice.
    """
    root = repo if repo is not None else _audited_repo_root(package)
    if root is None:
        return False
    from .._config import load_config

    return load_config(root).has_capability("no-mcp")


def mcp_tools_allowlist(package: str, repo: Path | None) -> set[str] | None:
    """Return the package's declared MCP tool allowlist, or None if absent.

    Finer-grained alternative to the all-or-nothing `mcp_parity_exempt`: a
    package that intentionally exposes a curated MCP surface (rather than
    mirroring its whole Python API) lists exactly the tools it means to ship.
    When present, §6 verifies the registered tools match this set — no
    full-API mirror required, and no blanket skip of the check.

    Read from (first match wins):
      1. ``pyproject.toml`` → ``[tool.scitex_dev] mcp_tools_allowlist = [...]``
      2. ``.scitex/dev/config.yaml`` → ``audit: {mcp-tools-allowlist: [...]}``

    Names may be bare (``compute_metrics``) or prefixed (``ml_compute_metrics``);
    the §6 check normalizes both. ``skills_list`` / ``skills_get`` are always
    permitted and need not be listed.
    """
    root = repo if repo is not None else _audited_repo_root(package)
    if root is None:
        return None

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib

            data = tomllib.loads(pyproject.read_text(errors="ignore"))
            value = (
                data.get("tool", {}).get("scitex_dev", {}).get("mcp_tools_allowlist")
            )
            if isinstance(value, list):
                return {str(x) for x in value}
        except Exception:
            pass

    cfg = root / ".scitex" / "dev" / "config.yaml"
    if cfg.is_file():
        try:
            import yaml

            data = yaml.safe_load(cfg.read_text(errors="ignore")) or {}
            audit = data.get("audit") or {}
            value = audit.get("mcp-tools-allowlist")
            if isinstance(value, list):
                return {str(x) for x in value}
        except Exception:
            pass

    return None


# --------------------------------------------------------------------- #
# §6 — Python API parity                                                 #
# --------------------------------------------------------------------- #


def _python_api_names(package: str) -> set[str]:
    """Return public function/callable-operation names exported by `scitex_<pkg>`.

    Best-effort: imports the top-level module, reads `__all__` (or non-private
    attributes), and keeps callables that are neither classes/types nor typing
    aliases with a public ``typing.get_origin``. Callable/Literal aliases and
    parameterized containers describe values rather than executable operations;
    counting them produces false missing-tool findings. Ordinary functions and
    callable instances remain operations in both flat and nested layouts.

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
    # One operation re-exported both flat (`pkg.describe`) and nested
    # (`pkg.descriptive.describe`) is ONE operation: counting it twice made
    # every such function demand two MCP tools. Nested names whose (unwrapped)
    # function is already exported flat are skipped below.
    flat_ops = {
        id(_inspect.unwrap(v))
        for v in (getattr(mod, n, None) for n in names if isinstance(n, str))
        if callable(v)
        and not _inspect.isclass(v)
        and not _inspect.ismodule(v)
        and get_origin(v) is None
    }
    for n in names:
        if not isinstance(n, str):
            continue
        val = getattr(mod, n, None)
        if val is None or _inspect.isclass(val) or get_origin(val) is not None:
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
                    or get_origin(sub_val) is not None
                    or _inspect.ismodule(sub_val)
                    or not callable(sub_val)
                    or id(_inspect.unwrap(sub_val)) in flat_ops
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
    # Leaf-side package-type capability knob: ALIAS packages with no
    # first-party MCP surface declare ``audit.capabilities: [no-mcp]`` in
    # ``.scitex/dev/config.yaml``. §6 does not apply to them; skip it with a
    # VISIBLE "declared capability" notice (operator directive 2026-06-22).
    if declares_no_mcp(package, repo=repo):
        import click

        # Use click.echo(err=True) — NOT _emit("info", ...) — so the notice is
        # ALWAYS visible: the audit logger's default level is WARNING and would
        # swallow an info headline. The operator requires this skip to be
        # visible, not silent (directive 2026-06-22).
        click.echo(
            f"  [capability] {package}: §6 skipped (declared capability: no-mcp)"
            " — alias/no first-party MCP surface; parity does not apply to this"
            " package type",
            err=True,
        )
        return

    if is_mcp_parity_exempt(package, repo=repo):
        from .._emit import emit as _emit

        _emit(
            "info",
            f"{package}: §6 MCP-parity exempt by config "
            "([tool.scitex_dev] mcp_parity_exempt = true) — plotting/diagram-rich "
            "tool surface mirrors external methods with no Python-API counterpart",
        )
        return

    short = _short_name(package)
    # Normalize MCP names to compare against bare Python names.
    mcp_normalized = {n.removeprefix(f"{short}_") for n in tool_names}

    # Finer-grained opt-in: a declared allowlist scopes §6 to the curated
    # surface (registered tools must match the declaration) instead of the
    # full Python-API mirror.
    allowlist = mcp_tools_allowlist(package, repo=repo)
    if allowlist is not None:
        from .._emit import emit as _emit

        _emit(
            "info",
            f"{package}: §6 MCP-parity scoped to mcp_tools_allowlist "
            f"({len(allowlist)} declared) — checked against the curated surface, "
            "not the full Python API",
        )
        out.extend(_allowlist_violations(package, allowlist, mcp_normalized))
        return

    py_apis = _python_api_names(package)
    if not py_apis:
        return  # cannot establish parity; not the auditor's place to invent it.

    # A committed parity baseline turns the missing-tool half into a ratchet
    # (see `_mcp_parity_baseline`); the orphan half is unchanged.
    root = repo if repo is not None else _audited_repo_root(package)
    try:
        baseline = load_parity_baseline(root)
    except MalformedParityBaseline as exc:
        out.append(Violation(package, "§6", f"malformed parity baseline: {exc}"))
        return
    out.extend(_parity_violations(package, py_apis, mcp_normalized, baseline))
    if baseline is not None:
        import click

        # Visible, like the no-mcp notice: the backlog is the point of the
        # ratchet and must never be swallowed by the WARNING-level logger.
        missing = missing_python_apis(py_apis, mcp_normalized)
        click.echo(
            format_backlog_notice(package, missing, baseline, len(py_apis)),
            err=True,
        )


def record_parity_baseline(package: str, repo: Path | None) -> tuple[Path, int]:
    """Write `package`'s current §6 missing-tool set as its parity baseline.

    Uses the same discovery as the audit (`_resolve_mcp_server` + the
    `_python_api_names` walk), so the recorded set is exactly what the next
    audit run compares against. Refuses packages whose §6 is exempt or
    allowlist-scoped (a baseline would never be read) and packages without
    an audited tree or MCP server. Returns ``(path, n_recorded)``.
    """
    from ._mcp_audit import _isolated_streams, _list_tools
    from ._mcp_bridge import _resolve_mcp_server

    root = repo if repo is not None else _audited_repo_root(package)
    if root is None:
        raise ValueError(f"{package}: no audited tree to write a baseline into")
    if (
        declares_no_mcp(package, repo=root)
        or is_mcp_parity_exempt(package, repo=root)
        or mcp_tools_allowlist(package, repo=root) is not None
    ):
        raise ValueError(
            f"{package}: §6 is skipped or allowlist-scoped by config — a parity "
            "baseline would never be read"
        )
    with _isolated_streams():
        server = _resolve_mcp_server(package)
        if server is None:
            raise ValueError(f"{package}: no FastMCP instance found")
        tools = _list_tools(server)
    short = _short_name(package)
    mcp_normalized = {
        t.name.removeprefix(f"{short}_") for t in tools if getattr(t, "name", "")
    }
    missing = missing_python_apis(_python_api_names(package), mcp_normalized)
    return write_parity_baseline(root, missing), len(missing)


def _allowlist_violations(
    package: str, allowlist: set[str], mcp_normalized: set[str]
) -> list[Violation]:
    """§6 with an explicit allowlist: the registered tools must equal the
    declared ``mcp_tools_allowlist`` (``skills_list`` / ``skills_get`` always
    permitted). Flags tools the server exposes but didn't declare, and declared
    names with no registered tool — finer control than the boolean exemption.

    Split out (pure set comparison) so it is testable without import/registry
    I/O, mirroring :func:`_parity_violations`.
    """
    out: list[Violation] = []
    skill_tools = {"skills_list", "skills_get"}
    short = _short_name(package)
    allow_norm = {n.removeprefix(f"{short}_") for n in allowlist} - skill_tools
    actual = mcp_normalized - skill_tools

    undeclared = actual - allow_norm
    if undeclared:
        out.append(
            Violation(
                package,
                "§6",
                f"MCP tool(s) not in mcp_tools_allowlist: {sorted(undeclared)} "
                "— add them to the allowlist or remove the tool",
            )
        )

    missing = allow_norm - actual
    if missing:
        out.append(
            Violation(
                package,
                "§6",
                f"mcp_tools_allowlist names with no registered MCP tool: "
                f"{sorted(missing)} — register the tool or fix the allowlist",
            )
        )
    return out


__all__ = [
    "_allowlist_violations",
    "_check_api_parity",
    "_parity_violations",
    "_python_api_names",
    "_tool_matches_api",
    "is_mcp_parity_exempt",
    "mcp_tools_allowlist",
    "record_parity_baseline",
]
