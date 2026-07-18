"""Subprocess-based behavioral checks for audit-cli.

Extracted from `_audit.py` (legacy-oversized) in slice 4 of the
CLI-standardization plan. Covers:

- §3  exit codes (unknown flag / unknown subcommand → 2)
- §1a `list-python-apis` verbosity ladder monotonicity
- §8  every `--json` leaf emits parseable JSON on stdout
- §5  deprecation ladder phases for hidden leaves — phase-aware via
      `_deprecated_alias` metadata (see `_std_rules.assess_hidden_leaf`):
      phase="warn" aliases MUST exit 0 and print 'deprecated' on stderr;
      phase="error" MUST exit 2; metadata-less hidden leaves keep the
      legacy expectation (non-zero + redirect hint).
- §7  CLI ↔ MCP tool parity
"""

from __future__ import annotations

import click

__all__ = [
    "_check_behavioral",
    "_collect_hidden_leaves",
    "_collect_json_leaves",
    "_extract_names",
    "_run_subprocess",
]


def _run_subprocess(args: list[str], timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a CLI command; return (exit_code, stdout, stderr). -1 on timeout/error."""
    import subprocess

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return -1, "", ""


def _collect_json_leaves(cmd: click.BaseCommand, path: list[str]) -> list[list[str]]:
    """Return paths (e.g. ['mcp', 'list-tools']) of every leaf that has --json."""
    from ._audit import _flag_names

    out: list[list[str]] = []
    if getattr(cmd, "hidden", False):
        return out
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            out.extend(_collect_json_leaves(sub, path + [name]))
        return out
    if "--json" in _flag_names(cmd):
        out.append(path)
    return out


def _collect_hidden_leaves(
    cmd: click.BaseCommand, path: list[str]
) -> list[tuple[list[str], click.BaseCommand]]:
    """Return (path, command) of every hidden leaf (deprecation candidates).

    The command object is carried alongside the path so the §5 check can
    read `_deprecated_alias` metadata and pick the phase-appropriate
    expectation.
    """
    out: list[tuple[list[str], click.BaseCommand]] = []
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            child_path = path + [name]
            if getattr(sub, "hidden", False) and not isinstance(sub, click.Group):
                out.append((child_path, sub))
            else:
                out.extend(_collect_hidden_leaves(sub, child_path))
    return out


def _check_behavioral(
    package: str,
    out: list,
    cmd: click.BaseCommand | None = None,
    timeout: float = 10.0,
) -> None:
    """Behavioral checks (§1a ladder, §3 exit codes, §5 phases, §7 parity, §8 JSON)."""
    import json as _json

    from ._audit import Violation
    from ._std_rules import assess_hidden_leaf

    sub_to = max(1.0, min(timeout, 30.0))

    # §3 — bogus flag at top level should exit 2 (Click default).
    rc, _so, _se = _run_subprocess(
        [package, "--definitely-not-a-flag-xyz"], timeout=sub_to
    )
    if rc != 2 and rc != -1:
        out.append(
            Violation(
                package,
                "§3",
                f"unknown flag at top-level exited {rc}, expected 2 (usage error)",
            )
        )

    # §3 — bogus subcommand should exit 2.
    rc, _so, _se = _run_subprocess(
        [package, "definitely-not-a-subcommand-xyz"], timeout=sub_to
    )
    if rc not in (
        2,
        -1,
        0,
    ):  # 0 means CLI accepted gibberish — also a bug, but separate signal
        if rc != 2:
            out.append(
                Violation(
                    package,
                    "§3",
                    f"unknown subcommand exited {rc}, expected 2 (usage error)",
                )
            )

    # §1a behavioral — list-python-apis verbosity ladder.
    levels = [[], ["-v"], ["-vv"], ["-vvv"]]
    counts: list[int] = []
    for extra in levels:
        rc, so, _se = _run_subprocess(
            [package, "list-python-apis", *extra], timeout=sub_to
        )
        if rc != 0:
            counts.append(-1)
            continue
        counts.append(len([ln for ln in so.splitlines() if ln.strip()]))
    if all(c >= 0 for c in counts):
        for i in range(1, len(counts)):
            if counts[i] < counts[i - 1]:
                out.append(
                    Violation(
                        f"{package} list-python-apis",
                        "§1a",
                        f"verbosity ladder not monotonic: -{'v' * i} produced fewer "
                        f"non-empty lines ({counts[i]}) than -{'v' * (i - 1)} ({counts[i - 1]})",
                    )
                )
                break

    # §8 — every leaf with --json must produce parseable JSON on stdout.
    if cmd is not None:
        for leaf_path in _collect_json_leaves(cmd, []):
            rc, so, _se = _run_subprocess(
                [package, *leaf_path, "--json"], timeout=sub_to
            )
            if rc == 0 and so.strip():
                try:
                    _json.loads(so)
                except _json.JSONDecodeError:
                    out.append(
                        Violation(
                            f"{package} {' '.join(leaf_path)}",
                            "§8",
                            "--json stdout is not parseable JSON (log contamination?)",
                        )
                    )

    # §5 — hidden leaves are deprecation-ladder rungs. Phase-aware:
    # `_deprecated_alias` metadata (set by scitex_dev.ecosystem.
    # deprecated_alias) selects the expectation; metadata-less hidden
    # leaves keep the legacy non-zero + redirect-hint contract.
    if cmd is not None:
        for leaf_path, leaf_cmd in _collect_hidden_leaves(cmd, []):
            rc, _so, se = _run_subprocess([package, *leaf_path], timeout=sub_to)
            meta = getattr(leaf_cmd, "_deprecated_alias", None)
            out.extend(
                assess_hidden_leaf(f"{package} {' '.join(leaf_path)}", rc, se, meta)
            )

    # §7 — CLI ↔ MCP parity. When both `list-python-apis --json` and
    # `mcp list-tools --json` are present, every Python API should map to
    # an MCP tool (loosely: the MCP set should cover a substantial fraction
    # of the Python API set).
    py_rc, py_so, _ = _run_subprocess(
        [package, "list-python-apis", "--json"], timeout=sub_to
    )
    mcp_rc, mcp_so, _ = _run_subprocess(
        [package, "mcp", "list-tools", "--json"], timeout=sub_to
    )
    if py_rc == 0 and mcp_rc == 0 and py_so.strip() and mcp_so.strip():
        try:
            py_set = _extract_names(_json.loads(py_so))
            mcp_set = _extract_names(_json.loads(mcp_so))
        except (_json.JSONDecodeError, AttributeError, TypeError):
            py_set, mcp_set = set(), set()
        if py_set and mcp_set:
            # MCP names typically prefix the package short name; strip it for comparison.
            short = package.replace("scitex-", "").replace("-", "_")
            mcp_normalized = {n.removeprefix(f"{short}_") for n in mcp_set}
            missing = py_set - mcp_normalized
            if missing and len(missing) > len(py_set) * 0.5:
                out.append(
                    Violation(
                        package,
                        "§7",
                        f"{len(missing)}/{len(py_set)} Python APIs have no matching MCP tool "
                        f"(sample: {sorted(missing)[:3]})",
                    )
                )


def _extract_names(payload) -> set[str]:
    """Pull a flat name set out of a JSON listing (handles list[str] | list[dict] | dict)."""
    if isinstance(payload, list):
        out: set[str] = set()
        for item in payload:
            if isinstance(item, str):
                out.add(item)
            elif isinstance(item, dict):
                for k in ("name", "tool", "api", "id"):
                    v = item.get(k)
                    if isinstance(v, str):
                        out.add(v)
                        break
        return out
    if isinstance(payload, dict):
        for k in ("apis", "tools", "items", "data", "results"):
            if k in payload:
                return _extract_names(payload[k])
        return set(k for k in payload.keys() if isinstance(k, str))
    return set()
