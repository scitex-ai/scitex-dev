"""MCP-tool auditor — companion to `audit-cli`.

Walks each `scitex-*` package's `_mcp_server.mcp` instance (FastMCP) and the
matching umbrella bridge under `scitex._mcp_tools.<pkg>`; checks against the
canonical MCP convention in
`<scitex-python>/src/scitex/_skills/general/03_interface_03_mcp/`.

Rules (matching that skill's section numbers):

- §1   server registration  — one `FastMCP` per package, mount-pattern bridge,
                              no double prefix, no hand-wrap.
- §2   tool naming          — `<pkg>_<verb>_<noun>` snake_case, no banned
                              shapes / synonyms.
- §3   required subcommands — `mcp start | doctor | list-tools | show-installation`
                              on the package CLI (delegated to the existing
                              `audit-cli` walker).
- §4   list-tools ladder    — `-v|-vv|-vvv` + `--json` (behavioral, opt-in).
- §5   skills integration   — `<pkg>_skills_list` and `<pkg>_skills_get` exist.
- §6   Python-API parity    — every tool wraps a public Python API (and v.v.).

The auditor reuses every helper that already exists in `_audit.py`:
registry cascade, severity tiers, filter helpers, watchdog, stream isolation,
human/JSON emitters.
"""

from __future__ import annotations

import asyncio
import importlib
import re
from pathlib import Path

import click

from . import FLAT_KEEPERS  # noqa: F401  -- reserved for future verb checks
from ._audit import (
    Violation,
    _emit_human,
    _emit_json,
    _filter_violations,
    _isolated_streams,
    _load_registry,
    _max_severity,
    _PackageTimeout,
    _violation_to_dict,
    _watchdog,
)


# --------------------------------------------------------------------- #
# Helpers — locate the standalone MCP server + umbrella bridge          #
# --------------------------------------------------------------------- #


def _import_name(package: str) -> str:
    """`scitex-cloud` → `scitex_cloud`."""
    return package.replace("-", "_")


def _short_name(package: str) -> str:
    """`scitex-cloud` → `cloud`; `scitex-cloud-mcp` → `cloud_mcp`; `scitex` → `scitex`.

    Always a valid Python identifier suffix (no hyphens), usable both as a
    tool-name prefix and as a bridge-file basename.
    """
    if package == "scitex":
        return "scitex"
    if package.startswith("scitex-"):
        return package[len("scitex-") :].replace("-", "_")
    return package.replace("-", "_")


# Packages we never audit as MCP standalones (they have no user-facing
# `_mcp_server.mcp` instance of their own). The umbrella `scitex` mounts
# everything; *-mcp / *-server packages ARE the protocol servers.
_MCP_AUDIT_SKIP_PACKAGES = {"scitex"}


def _should_skip(package: str) -> bool:
    if package in _MCP_AUDIT_SKIP_PACKAGES:
        return True
    if package.endswith("-mcp") or package.endswith("-server"):
        return True
    return False


def _resolve_mcp_server(package: str):
    """Locate a `FastMCP` instance for `package`.

    Tries module candidates `scitex_<pkg>._mcp_server`, `scitex_<pkg>.mcp_server`
    and looks for a top-level `mcp` attribute that is a `FastMCP`. Returns the
    instance or None.
    """
    try:
        from fastmcp import FastMCP  # local import to keep the module light
    except ImportError:
        return None

    import_name = _import_name(package)
    candidates = [
        f"{import_name}._mcp_server",
        f"{import_name}.mcp_server",
        f"{import_name}._mcp.server",  # scitex-io shape
        f"{import_name}.mcp.server",
    ]
    for mod_name in candidates:
        try:
            mod = importlib.import_module(mod_name)
        except BaseException:
            # `BaseException` (not just `Exception`) — some packages call
            # `sys.exit(1)` at module-import time when their preconditions
            # fail (e.g. scitex-orochi when telegram-bot env vars are unset).
            # SystemExit derives from BaseException, so a plain `except Exception`
            # would let it propagate and kill the audit run.
            continue
        for attr in ("mcp", "server", "app"):
            obj = getattr(mod, attr, None)
            if isinstance(obj, FastMCP):
                return obj
    return None


def _list_tools(mcp_instance) -> list:
    """Run `mcp.list_tools()` synchronously; return a list of FunctionTool."""
    try:
        return asyncio.run(mcp_instance.list_tools())
    except RuntimeError:
        # Already in an event loop — rare in CLI context, but handle gracefully.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(mcp_instance.list_tools())
        finally:
            loop.close()


def _read_bridge_source(package: str) -> str | None:
    """Read `scitex/_mcp_tools/<short>.py`; None if absent."""
    short = _short_name(package)
    try:
        # Auditing the umbrella's private bridge package by design — this
        # is the one place where the umbrella path is intentional, not a
        # PA-304 violation. Use a function-local import (lazy) so PA-304's
        # module-level scan exempts it.
        import scitex._mcp_tools as bridge_pkg  # noqa: PA-304
    except Exception:
        return None
    pkg_dir = Path(getattr(bridge_pkg, "__file__", "")).parent
    bridge = pkg_dir / f"{short}.py"
    if not bridge.is_file():
        return None
    try:
        return bridge.read_text(encoding="utf-8")
    except OSError:
        return None


# --------------------------------------------------------------------- #
# §2 / §5 — tool-name discipline                                        #
# --------------------------------------------------------------------- #


# Banned synonyms — same "Avoid" column as the CLI catalog.
_TOOL_NAME_SYNONYMS: dict[str, str] = {
    "ls": "list",
    "rm": "delete",
    "drop": "delete",
    "destroy": "delete",
    "enumerate": "list",
    "display": "show",
    "print": "show",
    "cat": "show",
    "view": "show",
    "new": "create",
    "make": "create",
    "edit": "update",
    "modify": "update",
}

# Verbs whose object is implicit (passed as a parameter) — `io_save`, `audio_speak`,
# `stats_run` — bare `<pkg>_<verb>` is acceptable per the §2 examples table.
_OBJECT_FROM_PARAM_VERBS = {
    "save",
    "load",
    "read",
    "write",
    "fetch",
    "download",
    "upload",
    "speak",
    "say",
    "play",
    "render",
    "compose",
    "plot",
    "build",
    "run",
    "execute",
    "exec",
    "compile",
    "convert",
    "import",
    "export",
    "send",
    "publish",
    "deploy",
    "ship",
    "init",
    "start",
    "stop",
    "validate",
    "check",
    "test",
    "lint",
    "format",
    "audit",
    "sync",
    "pull",
    "push",
    "commit",
    "open",
    "close",
    "reset",
    "restore",
}

# Verbs that need a noun in the tool name (object isn't implicit).
_VERBS_NEED_NOUN = {
    "list",
    "show",
    "get",
    "find",
    "search",
    "describe",
    "inspect",
    "delete",
    "remove",
    "purge",
    "create",
    "add",
    "update",
    "edit",
    "rename",
    "move",
}


_VALID_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _check_tool_naming(
    package: str, tool_names: list[str], out: list[Violation]
) -> None:
    """§2 — `<pkg>_<verb>_<noun>` snake_case + no banned synonyms / shapes."""
    short = _short_name(package)
    expected_prefix = f"{short}_"

    for raw in tool_names:
        # snake_case sanity
        if not _VALID_NAME.match(raw):
            out.append(
                Violation(
                    f"{package}::{raw}",
                    "§2",
                    f"tool name '{raw}' not snake_case (expected lowercase + underscores only)",
                )
            )
            continue

        # Double-prefix detection (e.g. dev_dev_bulk_rename after a bad mount)
        if raw.startswith(f"{short}_{short}_"):
            out.append(
                Violation(
                    f"{package}::{raw}",
                    "§1",
                    f"double-prefix '{short}_{short}_*' — likely a Convention A "
                    "standalone whose tools already include the package prefix",
                )
            )
            continue

        # The tool name as visible from the umbrella must start with `<short>_`.
        # Standalone-source names omit it under Convention A (mount adds it);
        # we only check the prefix when the name is already prefixed.
        if "_" not in raw:
            out.append(
                Violation(
                    f"{package}::{raw}",
                    "§2",
                    f"tool name '{raw}' has no verb_noun split — single-token "
                    "tools are forbidden; use `<verb>_<noun>` even for read tools",
                )
            )
            continue

        # If the name is prefixed, strip and inspect the verb_noun tail.
        body = raw[len(expected_prefix) :] if raw.startswith(expected_prefix) else raw
        parts = body.split("_")
        # Bare-verb name `<pkg>_<verb>` is allowed when the verb naturally takes
        # its object as a parameter (`io_save`, `audio_speak`). Only flag when
        # the verb belongs to the "needs-noun" set (`list`, `show`, `delete`, …).
        if len(parts) < 2:
            verb = parts[0]
            # Only flag when the verb genuinely needs a noun (`list`, `show`,
            # `delete`, …). Bare `<pkg>_<verb>` is fine when the verb takes
            # its object as a parameter (`io_save`, `audio_speak`, `audio_transcribe`).
            if verb in _VERBS_NEED_NOUN:
                out.append(
                    Violation(
                        f"{package}::{raw}",
                        "§2",
                        f"tool name '{raw}' uses bare verb '{verb}' which needs "
                        f"a noun — use '{expected_prefix}{verb}_<noun>' "
                        f"(e.g. '{expected_prefix}{verb}_packages')",
                    )
                )
            continue

        verb = parts[0]
        if verb in _TOOL_NAME_SYNONYMS:
            preferred = _TOOL_NAME_SYNONYMS[verb]
            out.append(
                Violation(
                    f"{package}::{raw}",
                    "§2",
                    f"banned synonym verb '{verb}' — use '{preferred}' "
                    f"(rename to '{expected_prefix}{preferred}_{'_'.join(parts[1:])}')",
                )
            )

        # Double-underscore typo class
        if "__" in raw:
            out.append(
                Violation(
                    f"{package}::{raw}",
                    "§2",
                    f"tool name '{raw}' has '__' — typo class, use single underscore",
                )
            )


def _check_skills_pair(
    package: str, tool_names: set[str], out: list[Violation]
) -> None:
    """§5 — `<pkg>_skills_list` and `<pkg>_skills_get` must exist."""
    short = _short_name(package)
    for required in (f"{short}_skills_list", f"{short}_skills_get"):
        # Tools may be registered with or without the prefix depending on
        # convention; accept either.
        bare = required[len(short) + 1 :]
        if required not in tool_names and bare not in tool_names:
            out.append(
                Violation(
                    package,
                    "§5",
                    f"missing required skills tool '{required}' "
                    f"(or '{bare}' under Convention A standalone source)",
                )
            )


# --------------------------------------------------------------------- #
# §1 — bridge / mount-pattern discipline                                 #
# --------------------------------------------------------------------- #


_HAND_WRAP_DECORATOR = re.compile(r"@\s*mcp\s*\.\s*tool\s*\(")
_SAFE_MOUNT_CALL = re.compile(r"\bsafe_mount\s*\(")
_PLAIN_MOUNT_CALL = re.compile(r"\.\s*mount\s*\(")


def _check_bridge_pattern(
    package: str,
    out: list[Violation],
    *,
    read_bridge_source=None,
    resolve_mcp_server=None,
) -> None:
    """§1 — umbrella bridge must use `safe_mount` (or equivalent), not hand-wrap.

    Exempt when the standalone has no `<pkg>._mcp_server.mcp`: the bridge
    cannot `safe_mount` a non-existent server, so hand-wrapping is the
    only available option. The §1 rule only applies when the bridge
    *could* mount but chose not to.

    The optional ``read_bridge_source`` / ``resolve_mcp_server`` callables
    let tests inject fakes without monkey-patching the module.
    """
    if read_bridge_source is None:
        read_bridge_source = _read_bridge_source
    if resolve_mcp_server is None:
        resolve_mcp_server = _resolve_mcp_server
    src = read_bridge_source(package)
    if src is None:
        # No bridge → not flagged here; presence is checked under §6 parity.
        return
    short = _short_name(package)
    has_safe_mount = bool(_SAFE_MOUNT_CALL.search(src))
    has_plain_mount = bool(_PLAIN_MOUNT_CALL.search(src))
    has_hand_wrap = bool(_HAND_WRAP_DECORATOR.search(src))

    if has_hand_wrap and not (has_safe_mount or has_plain_mount):
        # Standalone-side check: if `<pkg>._mcp_server.mcp` doesn't
        # resolve, hand-wrap is the only option. Don't penalise the
        # standalone for the umbrella's choice when no alternative exists.
        if resolve_mcp_server(package) is None:
            return
        out.append(
            Violation(
                package,
                "§1",
                f"umbrella bridge `scitex/_mcp_tools/{short}.py` "
                "hand-wraps tools — convert to `safe_mount(mcp, sub_mcp, namespace=…)` "
                "(see scitex/_mcp_tools/cloud.py)",
            )
        )
        return  # don't double-report

    if has_plain_mount and not has_safe_mount:
        out.append(
            Violation(
                package,
                "§1",
                f"umbrella bridge `scitex/_mcp_tools/{short}.py` "
                "uses direct `mcp.mount(...)` — replace with `safe_mount(mcp, sub_mcp)` "
                "from `scitex._mcp_tools._compat` for FastMCP 2.x/3.x portability",
            )
        )


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


def _check_api_parity(package: str, tool_names: set[str], out: list[Violation]) -> None:
    """§6 — every Python API should map to an MCP tool (and vice versa)."""
    py_apis = _python_api_names(package)
    if not py_apis:
        return  # cannot establish parity; not the auditor's place to invent it.

    short = _short_name(package)
    # Normalize MCP names to compare against bare Python names.
    mcp_normalized = {n.removeprefix(f"{short}_") for n in tool_names}

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


# --------------------------------------------------------------------- #
# Single-package audit                                                   #
# --------------------------------------------------------------------- #


def _audit_one_mcp(
    package: str, behavioral: bool = False, timeout: float = 30.0
) -> tuple[str, list[Violation]]:
    """Audit a single package's MCP surface; return (status, violations).

    Status: "ok" | "warn" | "no-mcp-server" | "skip-not-standalone" | "not-auditable: <reason>".
    """
    if _should_skip(package):
        # Umbrella + protocol-server packages aren't user-facing MCP standalones.
        return "skip-not-standalone", []

    with _isolated_streams():
        mcp_instance = _resolve_mcp_server(package)

    out: list[Violation] = []

    # Bridge-pattern check works from the umbrella source alone — run it even
    # when the standalone can't be imported, so `mcp.mount(...)`-style drift
    # is still surfaced for legacy packages whose mcp module path is unusual.
    if mcp_instance is None:
        _check_bridge_pattern(package, out)
        if out:
            return "warn", out
        return "no-mcp-server", []

    # Enumerate tools (may itself be slow / fail) under stream isolation.
    tools = []
    try:
        with _isolated_streams():
            tools = _list_tools(mcp_instance)
    except Exception as e:
        return f"not-auditable: list_tools failed: {type(e).__name__}: {e}", []

    tool_names = [getattr(t, "name", "") for t in tools]
    tool_set = {n for n in tool_names if n}

    _check_tool_naming(package, tool_names, out)
    _check_skills_pair(package, tool_set, out)
    _check_bridge_pattern(package, out)
    _check_api_parity(package, tool_set, out)

    # Behavioral checks (§4 ladder + §3 subcommand presence) reuse the CLI
    # auditor's subprocess machinery to avoid duplicating it.
    if behavioral:
        _check_behavioral_mcp(package, tool_set, out, timeout=timeout)

    return ("ok" if not out else "warn"), out


def _check_behavioral_mcp(
    package: str, tool_names: set[str], out: list[Violation], timeout: float = 30.0
) -> None:
    """§3 / §4 — invoke `<cli> mcp …` subcommands and verify behavior."""
    from ._audit import _run_subprocess  # reuse

    # §3 — required mcp subcommands. Probe each via `--help`; expect exit 0.
    for sub in ("start", "doctor", "list-tools", "show-installation"):
        rc, _so, _se = _run_subprocess(
            [package, "mcp", sub, "--help"], timeout=max(2.0, min(timeout, 10.0))
        )
        if rc != 0 and rc != -1:
            out.append(
                Violation(
                    f"{package} mcp {sub}",
                    "§3",
                    f"missing required subcommand `mcp {sub}` (--help exited {rc})",
                )
            )

    # §4 — verbosity ladder. Each level should produce ⊇ output.
    levels = [[], ["-v"], ["-vv"], ["-vvv"]]
    counts: list[int] = []
    for extra in levels:
        rc, so, _se = _run_subprocess(
            [package, "mcp", "list-tools", *extra], timeout=max(2.0, min(timeout, 10.0))
        )
        counts.append(
            len([ln for ln in so.splitlines() if ln.strip()]) if rc == 0 else -1
        )
    if all(c >= 0 for c in counts):
        for i in range(1, len(counts)):
            if counts[i] < counts[i - 1]:
                out.append(
                    Violation(
                        f"{package} mcp list-tools",
                        "§4",
                        f"verbosity ladder not monotonic: -{'v' * i} produced fewer "
                        f"non-empty lines ({counts[i]}) than -{'v' * (i - 1)} "
                        f"({counts[i - 1]})",
                    )
                )
                break

    # §4 — --json must produce parseable JSON on stdout.
    rc, so, _se = _run_subprocess(
        [package, "mcp", "list-tools", "--json"], timeout=max(2.0, min(timeout, 10.0))
    )
    if rc == 0 and so.strip():
        import json as _json

        try:
            _json.loads(so)
        except _json.JSONDecodeError:
            out.append(
                Violation(
                    f"{package} mcp list-tools",
                    "§4",
                    "--json stdout is not parseable JSON (log contamination?)",
                )
            )


# --------------------------------------------------------------------- #
# Public entry points                                                    #
# --------------------------------------------------------------------- #


def run_audit_mcp(
    package: str,
    behavioral: bool = False,
    output_json: bool = False,
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
    timeout: float = 30.0,
) -> int:
    """Audit a single package's MCP surface (single-target mode)."""
    try:
        from ...._ecosystem import should_skip_audit
    except ImportError:
        should_skip_audit = lambda *_a, **_k: (False, "")  # noqa: E731
    skip, reason = should_skip_audit(package, "audit-mcp-tools")
    from .._emit import emit as _emit

    if skip:
        if output_json:
            rec = {"package": package, "status": f"skip-{reason}", "violations": []}
            _emit_json([rec], "single-package mode (mcp)")
        else:
            _emit("skip", f"{package}: {reason}")
        return 0
    status, violations = _audit_one_mcp(package, behavioral=behavioral, timeout=timeout)
    violations = _filter_violations(violations, rules, exclude, min_severity)
    if not violations and status == "warn":
        status = "ok"
    if output_json:
        rec = {
            "package": package,
            "status": status,
            "violations": [_violation_to_dict(v) for v in violations],
        }
        _emit_json([rec], "single-package mode (mcp)")
    else:
        if status == "no-mcp-server":
            _emit("info", f"{package}: no `_mcp_server.mcp` found — skipped")
        elif status == "skip-not-standalone":
            _emit(
                "info",
                f"{package}: not an MCP standalone (umbrella or protocol-server) — skipped",
            )
        else:
            _emit_human(package, status, violations)
    if status.startswith("not-auditable"):
        return 2
    return 1 if _max_severity(violations) == "error" else 0


def run_audit_mcp_all(
    behavioral: bool = False,
    output_json: bool = False,
    dry_run: bool = False,
    registry_path: str | Path | None = None,
    rules: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    min_severity: str | None = None,
    timeout: float = 30.0,
) -> int:
    """Audit every MCP-bearing package in the registry."""
    # Duplicate fd 1 and fd 2 *before* importing any audit target. Some
    # packages close fd 1 during import (MCP servers, asyncio bots).
    # Writing the final summary through these duplicates is the only way
    # to guarantee output reaches the user.
    import os as _os

    try:
        _safe_stdout_fd = _os.dup(1)
        _safe_stderr_fd = _os.dup(2)
    except OSError:
        _safe_stdout_fd = 1
        _safe_stderr_fd = 2

    registry, provenance = _load_registry(registry_path)
    targets: list[str] = []
    for name in registry:
        # Quick filter: a package is auditable if a standalone _mcp_server module
        # exists. We don't import here (deferred to per-target run).
        targets.append(name)

    if dry_run:
        if output_json:
            payload = {
                "registry_source": provenance,
                "dry_run": True,
                "targets": [{"package": n, "action": "audit-mcp"} for n in targets],
            }
            import json as _json

            click.echo(_json.dumps(payload, indent=2))
        else:
            click.echo(f"# registry: {provenance}")
            click.echo(f"# {len(targets)} package(s) — dry-run, no audit performed")
            for n in targets:
                click.echo(f"  audit-mcp    {n}")
        return 0

    records: list[dict] = []
    counts = {
        "ok": 0,
        "warn": 0,
        "no-mcp-server": 0,
        "skip-not-standalone": 0,
        "not-auditable": 0,
    }
    any_error = False
    for name in targets:
        wall_budget = max(timeout + 5.0, 10.0)
        try:
            with _watchdog(wall_budget):
                status, violations = _audit_one_mcp(
                    name, behavioral=behavioral, timeout=timeout
                )
        except _PackageTimeout:
            status, violations = (
                f"not-auditable: timed out after {wall_budget:.0f}s",
                [],
            )

        violations = _filter_violations(violations, rules, exclude, min_severity)
        if not violations and status == "warn":
            status = "ok"

        if not output_json:
            # Don't spam the human report with one line per non-MCP package.
            if status not in ("no-mcp-server", "skip-not-standalone"):
                _emit_human(name, status, violations)

        if _max_severity(violations) == "error" or status.startswith("not-auditable"):
            any_error = True

        records.append(
            {
                "package": name,
                "status": status,
                "violations": [_violation_to_dict(v) for v in violations],
            }
        )
        bucket = "not-auditable" if status.startswith("not-auditable") else status
        counts[bucket] = counts.get(bucket, 0) + 1

    # Accumulated side effects from importing 60+ packages (especially MCP
    # servers that close stdio on init) can leave sys.stdout / click.echo
    # unwritable. For the post-loop summary we bypass Python's stream
    # wrapping and write directly to fd 1 via os.write — guaranteed to
    # land in the user's terminal/pipe regardless of what packages did.
    import os as _os

    def _write1(text: str) -> None:
        try:
            _os.write(_safe_stdout_fd, text.encode("utf-8", errors="replace"))
        except OSError:
            # The duplicate is closed too — try the original fd 1 as last resort.
            try:
                _os.write(1, text.encode("utf-8", errors="replace"))
            except OSError:
                pass

    if output_json:
        import json as _json

        payload = {"registry_source": provenance, "results": records}
        _write1(_json.dumps(payload, indent=2) + "\n")
    else:
        _write1("\n")
        _write1(f"# registry: {provenance}\n")
        _write1(
            f"# summary: {counts['ok']} ok, {counts['warn']} warn, "
            f"{counts['no-mcp-server']} no-mcp-server, "
            f"{counts['skip-not-standalone']} skip-not-standalone, "
            f"{counts['not-auditable']} not-auditable\n"
        )
    return 1 if any_error else 0
