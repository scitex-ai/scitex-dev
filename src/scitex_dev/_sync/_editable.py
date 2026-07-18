#!/usr/bin/env python3
# Timestamp: 2026-07-05
# File: scitex_dev/_sync/_editable.py

"""Local editable install of ecosystem packages.

Split out of ``_local.py`` (which keeps the remote SSH-sync logic).

Installer policy
----------------
Prefer **uv** — the ecosystem's standard installer, also used in the CI
``.def`` — over ``python -m pip``. uv is 10-100x faster and resolves the
same wheels; we fall back to ``python -m pip`` when uv is not on PATH so
a missing uv never hard-breaks install. Before installing, bring uv + pip
to their latest versions (best-effort; a stale installer never aborts the
install).

Safety model (like the rest of ``_sync``): every entry point defaults to
``confirm=False`` (preview only). Pass ``confirm=True`` to execute.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .._core.config import DevConfig, load_config

# ---------------------------------------------------------------------------
# Installer command construction (uv-first, pip fallback)
# ---------------------------------------------------------------------------


def _install_cmd(path: Path) -> list[str]:
    """Editable-install argv for *path*, preferring uv over pip.

    Both forms pin the target interpreter to ``sys.executable`` — bare
    ``pip``/``uv`` can resolve a stray system Python (spartan's
    ``/usr/bin`` is 3.9 and fails on >=3.10 wheels).
    """
    if shutil.which("uv"):
        return [
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "-e",
            str(path),
            "-q",
        ]
    return [sys.executable, "-m", "pip", "install", "-e", str(path), "-q"]


def _upgrade_installer_cmds() -> list[list[str]]:
    """Argv list that brings the installers to their latest versions.

    With uv present: ``uv self update`` (uv is a standalone managed
    binary) + ``uv pip install --upgrade pip``. Without uv: plain
    ``python -m pip install --upgrade pip``.
    """
    if shutil.which("uv"):
        return [
            ["uv", "self", "update"],
            ["uv", "pip", "install", "--python", sys.executable, "--upgrade", "pip"],
        ]
    return [[sys.executable, "-m", "pip", "install", "--upgrade", "pip"]]


def _run_upgrade_installers() -> dict[str, Any]:
    """Best-effort upgrade of uv + pip; never fails the ensuing install.

    Records each command's outcome. A non-zero return code or a missing
    tool is reported but does not raise — a stale uv/pip is preferable to
    a hard install abort (e.g. ``uv self update`` legitimately fails when
    uv was installed via a package manager rather than as a standalone
    binary).
    """
    steps: list[dict[str, Any]] = []
    ok = True
    for cmd in _upgrade_installer_cmds():
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300
            )
            step_ok = proc.returncode == 0
            detail = (proc.stdout or proc.stderr or "").strip()
            steps.append(
                {
                    "cmd": " ".join(cmd),
                    "status": "ok" if step_ok else "error",
                    "detail": detail[-500:],
                }
            )
            ok = ok and step_ok
        except Exception as e:  # noqa: BLE001 — best-effort, report and continue
            steps.append(
                {"cmd": " ".join(cmd), "status": "error", "detail": str(e)}
            )
            ok = False
    return {"status": "ok" if ok else "error", "steps": steps}


def _install_one(pkg, path: Path) -> tuple[str, dict[str, Any]]:
    """Editable-install one package (uv-first); return ``(name, result)``."""
    try:
        result = subprocess.run(
            _install_cmd(path),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            return pkg.name, {"status": "ok", "output": result.stdout.strip()}
        return pkg.name, {"status": "error", "error": result.stderr.strip()}
    except Exception as e:
        return pkg.name, {"status": "error", "error": str(e)}


def sync_local(
    packages: list[str] | None = None,
    confirm: bool = False,
    config: DevConfig | None = None,
    jobs: int = 1,
    on_progress=None,
) -> dict[str, Any]:
    """Install all local editable packages (uv-first, pip fallback).

    Before installing, brings uv + pip to their latest versions
    (best-effort — reported under the reserved ``_preflight`` key).

    Safety: defaults to preview only. Pass confirm=True to execute.

    Parameters
    ----------
    packages : list[str] | None
        Package names. None = all configured packages.
    confirm : bool
        If False (default), preview only.
        If True, execute the upgrade preflight + editable installs.
    config : DevConfig | None
        Configuration.
    jobs : int
        Parallel installs. 1 = serial (default). 0 or negative = all CPUs.
    on_progress : callable | None
        Optional callback ``f(idx, total, name, status, elapsed)`` invoked
        as each package finishes.

    Returns
    -------
    dict
        ``{package: {status, output|commands|error}}`` plus a reserved
        ``_preflight`` entry describing the uv/pip upgrade (its
        ``commands`` in dry-run, its per-step results when executed).
    """
    import os
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if config is None:
        config = load_config()

    targets = config.packages
    if packages:
        targets = [p for p in targets if p.name in packages]

    # Resolve installable targets (skip missing-path early)
    work: list[tuple[Any, Path]] = []
    results: dict[str, Any] = {}
    for pkg in targets:
        if not pkg.local_path:
            continue
        path = Path(pkg.local_path).expanduser()
        if not path.exists():
            results[pkg.name] = {"status": "skipped", "error": f"{path} not found"}
            continue
        if not confirm:
            results[pkg.name] = {"status": "dry_run", "commands": _install_cmd(path)}
            continue
        work.append((pkg, path))

    # Dry-run: also surface the uv+pip upgrade preflight that WOULD run.
    if not confirm:
        if any(r.get("status") == "dry_run" for r in results.values()):
            results["_preflight"] = {
                "status": "dry_run",
                "commands": _upgrade_installer_cmds(),
            }
        return results

    if not work:
        return results

    # Preflight: bring uv + pip to latest once, before any package install.
    results["_preflight"] = _run_upgrade_installers()

    # Resolve --jobs
    if jobs <= 0:
        jobs = os.cpu_count() or 1
    jobs = max(1, min(jobs, len(work)))

    total = len(work)
    started = {pkg.name: time.monotonic() for pkg, _ in work}

    if jobs == 1:
        # Serial path — preserve deterministic ordering
        for idx, (pkg, path) in enumerate(work, 1):
            name, res = _install_one(pkg, path)
            results[name] = res
            if on_progress is not None:
                on_progress(
                    idx, total, name, res["status"], time.monotonic() - started[name]
                )
    else:
        # Parallel path — editable install is mostly I/O (git, PyPI metadata)
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futures = {
                ex.submit(_install_one, pkg, path): pkg.name for pkg, path in work
            }
            for idx, fut in enumerate(as_completed(futures), 1):
                name, res = fut.result()
                results[name] = res
                if on_progress is not None:
                    on_progress(
                        idx,
                        total,
                        name,
                        res["status"],
                        time.monotonic() - started[name],
                    )

    return results


# EOF
