#!/usr/bin/env python3
# Timestamp: 2026-02-24
# File: scitex_dev/sync.py

"""Ecosystem package sync across local and remote hosts.

Safety model (like bulk_rename):
  - All operations default to dry_run=True (preview only).
  - Pass confirm=True to actually execute.
  - CLI requires --confirm flag.
  - MCP tool requires confirm=True parameter.
"""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .._core.config import DevConfig, HostConfig, get_enabled_hosts, load_config

# Local editable install lives in its own module (uv-first installer +
# upgrade preflight); re-exported here so the historical
# ``from ._local import sync_local`` import path keeps working.
from ._editable import sync_local  # noqa: F401,E402

# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------


def _build_ssh_args(host: HostConfig) -> list[str]:
    """Build SSH command prefix for a host."""
    args = ["ssh"]
    if host.ssh_key:
        args.extend(["-i", host.ssh_key])
    if host.port != 22:
        args.extend(["-p", str(host.port)])
    args.extend(
        [
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
        ]
    )
    args.append(f"{host.user}@{host.hostname}")
    return args


def _get_host_packages(host: HostConfig, config: DevConfig) -> list[tuple[str, str]]:
    """Get (package_name, remote_dir_name) pairs for a host.

    Resolution: legacy ``host.packages`` allow-list wins; otherwise
    default to all ecosystem packages minus ``host.exclude``.
    """
    pkg_map = {p.name: p for p in config.packages}
    if host.packages:
        names = list(host.packages)
    else:
        excluded = set(host.exclude or [])
        names = [p.name for p in config.packages if p.name not in excluded]
    out = []
    for name in names:
        pkg = pkg_map.get(name)
        if pkg and pkg.local_path:
            out.append((name, Path(pkg.local_path).expanduser().name))
    return out


def _build_sync_commands(
    host: HostConfig, dir_name: str, stash: bool, install: bool
) -> list[str]:
    """Build the shell commands that would be run for a package."""
    base = f"{host.remote_base}/{dir_name}"
    cmds = [f"cd {base}"]
    if install:
        # Ensure .venv symlink exists so pip resolves to the right env
        cmds.append("test -e .venv || ln -s ~/.venv .venv 2>/dev/null || true")
    if stash:
        cmds.append("git stash")
    cmds.append("git pull")
    if install:
        cmds.append(f"{host.pip_bin} install -e . -q")
    if stash:
        cmds.append("git stash pop 2>/dev/null || true")
    return cmds


def _check_ahead_state(
    host: HostConfig,
    dir_name: str,
    *,
    subprocess_run=None,
) -> dict[str, Any]:
    """Inspect the remote working copy's position vs. its upstream.

    Returns a dict with ``status`` in:
      - ``clean``: up-to-date or only behind upstream (safe to pull).
      - ``ahead``: remote-side has unpushed commits — fast-forward pull
        would be blocked; skip to avoid clobbering local work.
      - ``diverged``: both ahead and behind — needs human decision.
      - ``missing``: repo dir or git metadata absent.
      - ``error``: SSH/git failure; see ``error`` field.

    Also returns ``local_ahead`` (remote-side commits ahead of
    ``@{u}``) and ``remote_ahead`` (``@{u}`` commits ahead of HEAD).
    "Local" here is confusingly the *remote host's* working copy —
    the caller is on some other machine.
    """
    base = f"{host.remote_base}/{dir_name}"
    # Single-line remote script — uses unique sentinels so output parsing
    # survives line-wrap/colorization from git or shell integrations.
    remote_cmd = (
        f"cd {base} 2>/dev/null || {{ echo SACDEV_MISSING; exit 0; }}; "
        "if [ ! -d .git ]; then echo SACDEV_MISSING; exit 0; fi; "
        "git fetch -q 2>/dev/null || true; "
        'la=$(git rev-list --count "@{u}..HEAD" 2>/dev/null || echo 0); '
        'ra=$(git rev-list --count "HEAD..@{u}" 2>/dev/null || echo 0); '
        "echo SACDEV_STATE la=$la ra=$ra"
    )
    ssh_args = _build_ssh_args(host)
    ssh_args.append(remote_cmd)
    runner = subprocess_run if subprocess_run is not None else subprocess.run
    try:
        result = runner(ssh_args, capture_output=True, text=True, timeout=60)
        stdout = result.stdout.strip()
        if result.returncode != 0:
            return {
                "status": "error",
                "error": (result.stderr.strip() or f"exit {result.returncode}"),
            }
        if "SACDEV_MISSING" in stdout:
            return {"status": "missing"}
        # Parse: "SACDEV_STATE la=X ra=Y"
        la, ra = 0, 0
        for tok in stdout.split():
            if tok.startswith("la="):
                la = int(tok[3:] or 0)
            elif tok.startswith("ra="):
                ra = int(tok[3:] or 0)
        if la > 0 and ra > 0:
            status = "diverged"
        elif la > 0:
            status = "ahead"
        else:
            status = "clean"
        return {"status": status, "local_ahead": la, "remote_ahead": ra}
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "ahead-check SSH timed out (60s)"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _sync_one_package(
    host: HostConfig,
    dir_name: str,
    stash: bool,
    install: bool,
    safe: bool = True,
    *,
    subprocess_run=None,
    check_ahead_state_fn=None,
) -> dict[str, Any]:
    """Sync a single package on a remote host.

    When ``safe`` is True (default), first check whether the remote
    working copy has unpushed commits; if so, skip to avoid clobbering.
    This matches the user instruction: if remote is ahead, compare and
    skip when a decision is unclear.
    """
    check_ahead = (
        check_ahead_state_fn if check_ahead_state_fn is not None else _check_ahead_state
    )
    runner = subprocess_run if subprocess_run is not None else subprocess.run
    if safe:
        ahead = check_ahead(host, dir_name)
        if ahead["status"] in {"ahead", "diverged"}:
            return {
                "status": f"skipped_{ahead['status']}",
                "local_ahead": ahead.get("local_ahead", 0),
                "remote_ahead": ahead.get("remote_ahead", 0),
                "reason": (
                    "remote working copy has unpushed commits; resolve manually "
                    "(push / rebase / reset) then re-run sync"
                ),
            }
        if ahead["status"] == "missing":
            return {"status": "missing", "reason": "package dir not on remote"}
        if ahead["status"] == "error":
            return {
                "status": "error",
                "error": ahead.get("error", "ahead-check failed"),
            }

    cmds = _build_sync_commands(host, dir_name, stash, install)
    remote_cmd = " && ".join(cmds)

    ssh_args = _build_ssh_args(host)
    ssh_args.append(remote_cmd)

    try:
        result = runner(ssh_args, capture_output=True, text=True, timeout=120)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            return {"status": "ok", "output": stdout}
        return {
            "status": "error",
            "output": stdout,
            "error": stderr or f"exit code {result.returncode}",
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "SSH command timed out (120s)"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Public API — all default to dry_run=True (safe preview)
# ---------------------------------------------------------------------------


def sync_host(
    host: HostConfig,
    packages: list[str] | None = None,
    stash: bool = True,
    install: bool = True,
    safe: bool = True,
    confirm: bool = False,
    config: DevConfig | None = None,
    *,
    host_packages_fn=None,
) -> dict[str, Any]:
    """Sync packages to a remote host via SSH.

    Safety: defaults to preview only. Pass confirm=True to execute.

    Steps per package: ahead-check (if safe), git stash, git pull,
    pip install -e ., git stash pop.

    Parameters
    ----------
    host : HostConfig
        Target host configuration.
    packages : list[str] | None
        Package names to sync. None = use host's configured packages.
    stash : bool
        Git stash before pull (default True).
    install : bool
        Pip install after pull (default True).
    safe : bool
        If True (default), pre-check each remote working copy and skip
        packages whose HEAD is ahead of / diverged from upstream so we
        never clobber unpushed commits.
    confirm : bool
        If False (default), preview only (dry run).
        If True, execute the sync operation.
    config : DevConfig | None
        Configuration. Loaded from default if None.

    Returns
    -------
    dict
        Per-package results: {package: {status, commands|output, error}}.
        ``status`` includes ``ok``, ``skipped_ahead``, ``skipped_diverged``,
        ``missing``, ``error``, ``timeout``, or ``dry_run``.
    """
    if config is None:
        config = load_config()

    get_host_pkgs = (
        host_packages_fn if host_packages_fn is not None else _get_host_packages
    )
    host_pkgs = get_host_pkgs(host, config)
    if packages:
        host_pkgs = [(n, d) for n, d in host_pkgs if n in packages]

    if not confirm:
        return {
            name: {
                "status": "dry_run",
                "commands": _build_sync_commands(host, dir_name, stash, install),
                "safe_check": safe,
            }
            for name, dir_name in host_pkgs
        }

    # Parallel package sync within a single host
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(
                _sync_one_package, host, dir_name, stash, install, safe
            ): name
            for name, dir_name in host_pkgs
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
    return results


def sync_all(
    hosts: list[str] | None = None,
    packages: list[str] | None = None,
    stash: bool = True,
    install: bool = True,
    safe: bool = True,
    confirm: bool = False,
    config: DevConfig | None = None,
    *,
    sync_host_fn=None,
    enabled_hosts_fn=None,
) -> dict[str, Any]:
    """Sync packages across all enabled hosts.

    Safety: defaults to preview only. Pass confirm=True to execute.
    Parallel: hosts are synced concurrently by default.

    Parameters
    ----------
    hosts : list[str] | None
        Host names to sync. None = all enabled hosts.
    packages : list[str] | None
        Package names. None = host-specific defaults.
    stash : bool
        Git stash before pull.
    install : bool
        Pip install after pull.
    safe : bool
        If True (default), skip packages whose remote working copy is
        ahead of / diverged from upstream (never clobber unpushed work).
    confirm : bool
        If False (default), preview only (dry run).
        If True, execute the sync operation.
    config : DevConfig | None
        Configuration.

    Returns
    -------
    dict
        {host_name: {package: result}}.
    """
    if config is None:
        config = load_config()

    enabled_fn = enabled_hosts_fn if enabled_hosts_fn is not None else get_enabled_hosts
    do_sync_host = sync_host_fn if sync_host_fn is not None else sync_host

    enabled = enabled_fn(config)
    if hosts:
        enabled = [h for h in enabled if h.name in hosts]

    if not confirm:
        # Dry-run: no SSH needed, compute locally
        return {
            host.name: do_sync_host(
                host,
                packages=packages,
                stash=stash,
                install=install,
                safe=safe,
                confirm=False,
                config=config,
            )
            for host in enabled
        }

    # Execute: parallel across hosts
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(enabled) or 1) as executor:
        futures = {
            executor.submit(
                do_sync_host,
                host,
                packages=packages,
                stash=stash,
                install=install,
                safe=safe,
                confirm=True,
                config=config,
            ): host.name
            for host in enabled
        }
        for future in as_completed(futures):
            host_name = futures[future]
            try:
                results[host_name] = future.result()
            except Exception as e:
                results[host_name] = {"error": str(e)}
    return results


# EOF
