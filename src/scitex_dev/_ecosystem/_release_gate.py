#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Release gate — assert a package's PyPI-installed version has reached
full fleet coverage before a protocol-breaking release proceeds.

Background (2026-07-10 scitex-todo outage)
--------------------------------------------
scitex-todo shipped a new enum value ("cancelled") into the shared
``tasks.yaml`` store that only its own newer build understood. Every
other fleet host running an older scitex-todo build hard-failed
loading the shared store (strict validation on unknown enum values) —
a multi-hour outage. The fix has two halves:

  1. scitex-todo's own half: a tolerant reader (unknown status VALUES
     load with a loud warning instead of hard-failing; writes stay
     strict). Out of scope here — that is scitex-todo's own model
     file, not this module's concern.
  2. scitex-dev's half (THIS module): a generic, reusable mechanism so
     a protocol-breaking release can never go out again before every
     fleet host has the tolerant/compatible reader installed.

Convention — marking a "protocol milestone" release
-----------------------------------------------------
When a package is about to ship a release that BREAKS an older
reader (new required field, new enum value a strict old parser
chokes on, etc.), the fix ships in two releases:

  - release N   (e.g. ``scitex-todo==0.7.51``): adds the tolerant
    reader, otherwise backward compatible. This is the "protocol
    milestone" — it must reach 100% installed-coverage across the
    fleet before release N+1 is cut.
  - release N+1 (e.g. ``scitex-todo==0.8.0``): makes the actual
    breaking change (removes a legacy enum value, etc.).

Marking release N as a milestone needs no separate registry entry —
the convention IS the CLI invocation. A repo's release workflow (CI
job, pre-tag hook, or a human/agent cutting the tag) runs::

    scitex-dev ecosystem validate-versions \\
        --gate scitex-todo==0.7.51 --require-full-coverage

referencing release N's version directly. The command hard-blocks
(non-zero exit) until every in-scope fleet host reports scitex-todo
``>= 0.7.51`` installed. Once it passes, release N+1 is safe to cut.

Scope note — what "fleet coverage" means here
-----------------------------------------------
This reuses the SAME host-probing infrastructure ``ecosystem
validate-versions`` already uses for git-SHA sync auditing
(``scitex_dev._core.config`` hosts + SSH,
``scitex_dev._ecosystem._packages``). "Coverage" is measured per
CONFIGURED HOST (``~/.scitex/dev/config.yaml`` hosts: nas, spartan,
mba, …), each queried once via ``pip show`` for its installed version
of the package. This is a deliberate, honest simplification:
scitex-dev has no visibility into individual sac-agent-container
site-packages independent of the host they run on (that's
scitex-agent-container's domain, not scitex-dev's) — but agents
sharing a host's Python environment / container image typically share
its installed version, so host-level coverage is a reasonable,
currently-achievable proxy for fleet coverage.

A host is IN SCOPE for the gate iff the package is in that host's
synced-package set (the same allow-list / ``exclude:`` semantics
``ecosystem validate-versions`` already uses via
``scitex_dev._sync._get_host_packages``) — hosts that don't track the
package at all are simply absent from the result, not counted as
failing. An EMPTY in-scope set means the gate inspected nothing and is
treated as NOT passed (see ``check_release_gate``).
"""

from __future__ import annotations

import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from .._core.config import DevConfig, HostConfig, get_enabled_hosts, load_config
from .._sync import _build_ssh_args, _get_host_packages

RemoteVersionFn = Callable[[HostConfig, str], "str | None"]


def _version_tuple(text: str | None) -> tuple[int, ...]:
    """Lossy SemVer-ish parse — leading numeric dot components.

    ``"0.7.51"`` -> ``(0, 7, 51)``. A non-numeric trailer
    (``"1.2.0rc1"``) stops the scan at the first non-numeric chunk:
    ``(1, 2, 0)``. Empty / unparseable input returns ``()``.
    """
    parts: list[int] = []
    for chunk in re.split(r"[.]", (text or "").strip()):
        m = re.match(r"^(\d+)", chunk)
        if not m:
            break
        parts.append(int(m.group(1)))
    return tuple(parts)


def _version_gte(installed: str | None, minimum: str) -> bool:
    """True iff ``installed`` parses to a version >= ``minimum``.

    Fail-safe: missing / unparseable versions on either side return
    ``False`` (never silently treat "unknown" as "meets the gate").
    """
    a = _version_tuple(installed)
    b = _version_tuple(minimum)
    if not a or not b:
        return False
    return a >= b


def _remote_pip_version(host: HostConfig, pypi_name: str) -> str | None:
    """SSH to *host* and read the installed version of *pypi_name*.

    Uses the host's configured ``pip_bin`` (falls back to plain
    ``pip`` when unset) so the check matches whichever Python
    environment that host's editable installs actually run in.
    Returns ``None`` for "not installed" or any SSH/parse error — the
    caller treats ``None`` as "does not meet the gate" (fail-safe).
    """
    pip_bin = host.pip_bin or "pip"
    cmd = f"{pip_bin} show {pypi_name} 2>/dev/null || true"
    args = _build_ssh_args(host) + [cmd]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip()
    return None


def collect_gate_state(
    package: str,
    min_version: str,
    hosts: list[str] | None = None,
    config: DevConfig | None = None,
    *,
    remote_version_fn: RemoteVersionFn | None = None,
) -> dict[str, Any]:
    """Probe every in-scope host's installed version of *package*.

    Parameters
    ----------
    package : str
        The scitex-dev ecosystem package NAME (e.g. ``"scitex-todo"``,
        matching ``PackageConfig.name``) — NOT necessarily the PyPI
        distribution name, though they're usually equal. Resolved to
        ``PackageConfig.pypi_name`` for the actual ``pip show`` call.
    min_version : str
        The gate threshold, e.g. ``"0.7.51"``.
    hosts : list[str] | None
        Restrict to these host names. ``None`` = all enabled hosts.
    remote_version_fn : callable | None
        Injectable seam for tests — ``(HostConfig, pypi_name) -> str |
        None``. Defaults to a real SSH ``pip show``.

    Returns
    -------
    dict
        ``{"package", "pypi_name", "min_version", "rows": [{"host",
        "installed": str | None, "meets": bool}, ...]}``. ``rows``
        only contains hosts where *package* is in that host's synced
        set — an out-of-scope host is simply absent, not counted.
    """
    if config is None:
        config = load_config()

    remote_fn = (
        remote_version_fn if remote_version_fn is not None else _remote_pip_version
    )

    pkg = next((p for p in config.packages if p.name == package), None)
    pypi_name = pkg.pypi_name if pkg else package

    enabled = get_enabled_hosts(config)
    if hosts:
        enabled = [h for h in enabled if h.name in hosts]

    in_scope: list[HostConfig] = []
    for host in enabled:
        host_pkg_names = {n for n, _ in _get_host_packages(host, config)}
        if package in host_pkg_names:
            in_scope.append(host)

    rows: list[dict[str, Any]] = []
    if in_scope:
        with ThreadPoolExecutor(max_workers=min(16, len(in_scope))) as ex:
            fut_map = {ex.submit(remote_fn, h, pypi_name): h for h in in_scope}
            for fut in as_completed(fut_map):
                host = fut_map[fut]
                try:
                    installed = fut.result()
                except Exception:
                    installed = None
                rows.append(
                    {
                        "host": host.name,
                        "installed": installed,
                        "meets": _version_gte(installed, min_version),
                    }
                )

    rows.sort(key=lambda r: r["host"])
    return {
        "package": package,
        "pypi_name": pypi_name,
        "min_version": min_version,
        "rows": rows,
    }


def gate_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Coverage stats + the list of hosts NOT meeting the gate."""
    rows = state["rows"]
    total = len(rows)
    covered = sum(1 for r in rows if r["meets"])
    not_covered = [r["host"] for r in rows if not r["meets"]]
    coverage_pct = (100.0 * covered / total) if total else 0.0
    return {
        "total_hosts": total,
        "covered": covered,
        "coverage_pct": coverage_pct,
        "not_covered": not_covered,
    }


def check_release_gate(
    package: str,
    min_version: str,
    hosts: list[str] | None = None,
    config: DevConfig | None = None,
    *,
    remote_version_fn: RemoteVersionFn | None = None,
) -> dict[str, Any]:
    """Top-level entry: gate state + summary + pass/fail.

    ``passed`` is True iff every in-scope host meets ``min_version``.
    An EMPTY in-scope host set (``summary.total_hosts == 0``) is
    treated as NOT passed — a gate that inspected nothing proves
    nothing; the caller almost certainly has a config problem (package
    missing from every host's synced set) and must not silently
    green-light a release on that basis.
    """
    state = collect_gate_state(
        package,
        min_version,
        hosts=hosts,
        config=config,
        remote_version_fn=remote_version_fn,
    )
    summary = gate_summary(state)
    passed = summary["total_hosts"] > 0 and not summary["not_covered"]
    return {**state, "summary": summary, "passed": passed}


# EOF
