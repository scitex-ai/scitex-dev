#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``deploy-freshness`` cron body — ecosystem-level drift detector.

Lives under ``_ecosystem_jobs/`` (not ``_cli/cron/``) because it is a
CROSS-PACKAGE control-plane job, not one of scitex-dev's own
package-internal crons. Installed via the federated path:
``scitex-dev ecosystem cron`` discovers it through the
``scitex_dev.jobs`` entry-point group that scitex-dev itself
registers (treating scitex-dev as a leaf of itself — the dual-mode
principle applied to scitex-dev).

The bug this catches
--------------------
The operator pulled scitex-todo develop on ``/work`` to get UI updates,
but the systemd ``--user`` unit on port 8051 was installed against the
PyPI wheel from before the pull. The unit kept serving the stale code
invisibly until the operator noticed the missing UI feature. This cron
job closes the loop: it scans every JobSpec of kind ``"service"`` or
``"timer"`` discovered via ``scitex_dev.jobs.discover_jobs``, maps each
command's first token to its owning Python distribution via
``importlib.metadata.entry_points``, compares the installed version to
the latest on PyPI, and (with ``--apply``) runs ``pip install -U`` +
``systemctl --user restart <unit>`` so the next request sees the new
version.

Schedule
--------
``*/30 * * * *`` (every 30 min). Fast enough to catch drift before the
operator notices, infrequent enough not to thrash PyPI.

Robustness
----------
Drift detection runs on every tick; repair is gated behind ``--apply``
(the production crontab line passes ``--apply``). Each per-service step
is failure-isolated:

* PyPI 503 → logged + skipped, the next tick retries.
* ``pip install`` failure → logged + the service stays on the stale
  version (no auto-rollback ceremony — operator inspects manually if
  the audit log shows repeated failures).
* ``systemctl restart`` failure → logged + counted, the loop keeps
  reconciling the rest of the services.

Exit code is non-zero only when the whole sweep itself errors (the
``discover_jobs`` call raises, config-level mis-setup, etc.) — never
on a per-service hiccup the next tick will sort out.

Seams (PA-306 / STX-NM)
-----------------------
``http_runner``, ``pip_runner``, ``systemctl_runner``, ``which`` and
``metadata_lookup`` are keyword arguments — tests pass real fakes and
``tmp_path``-rooted log files without ``unittest.mock`` or
``monkeypatch``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Paths / defaults
# ---------------------------------------------------------------------------


def _default_log_path() -> Path:
    """Return ``~/.scitex/dev/logs/cron-deploy-freshness.log`` (env-aware)."""
    import os

    base = os.environ.get("SCITEX_DIR") or os.path.join(
        os.path.expanduser("~"), ".scitex"
    )
    return Path(base) / "dev" / "logs" / "cron-deploy-freshness.log"


_PYPI_JSON_URL = "https://pypi.org/pypi/{name}/json"
_HTTP_TIMEOUT_S = 10.0
_PIP_TIMEOUT_S = 180.0
_SYSTEMCTL_TIMEOUT_S = 30.0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceOutcome:
    """Per-service outcome of one ``deploy-freshness`` sweep."""

    job_name: str
    binary: str | None
    package: str | None
    installed_version: str | None
    latest_version: str | None
    drift: bool
    action: str  # ok / would-update / updated / skipped / error
    detail: str = ""


@dataclass(frozen=True)
class DeployFreshnessResult:
    """Aggregate outcome of one ``deploy-freshness`` cron tick."""

    log_path: str
    services_checked: int = 0
    drift_count: int = 0
    updated_count: int = 0
    error_count: int = 0
    outcomes: tuple[ServiceOutcome, ...] = field(default_factory=tuple)
    error: str | None = None


# ---------------------------------------------------------------------------
# Default runners (test-fakable)
# ---------------------------------------------------------------------------


def _default_http_runner(url: str, timeout: float) -> tuple[int, bytes]:
    """Real ``urllib`` GET. Tests pass their own fake."""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.getcode(), resp.read()


def _default_pip_runner(args: list[str]) -> subprocess.CompletedProcess:
    """Real ``pip`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["pip", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=_PIP_TIMEOUT_S,
    )


def _default_systemctl_runner(
    args: list[str],
    *,
    timeout: float = _SYSTEMCTL_TIMEOUT_S,
) -> subprocess.CompletedProcess:
    """Real ``systemctl --user`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Helpers — pure, test-friendly
# ---------------------------------------------------------------------------


def _extract_binary(command: str) -> str | None:
    """Return the first token of ``command`` (the executable path/name)."""
    import shlex

    tokens = shlex.split(command or "")
    if not tokens:
        return None
    return tokens[0]


def _binary_basename(binary: str) -> str:
    """Return the basename of ``binary``."""
    return Path(binary).name


def _resolve_owning_distribution(
    binary: str,
    *,
    metadata_lookup=metadata.entry_points,
) -> tuple[str, str] | None:
    """Return ``(distribution_name, installed_version)`` for the console
    script ``binary``, or ``None`` if no console-script entry matches.
    """
    name = _binary_basename(binary)
    try:
        eps = metadata_lookup(group="console_scripts")
    except TypeError:
        eps = [ep for ep in metadata_lookup() if ep.group == "console_scripts"]
    for ep in eps:
        if ep.name != name:
            continue
        dist = getattr(ep, "dist", None)
        if dist is None:
            continue
        try:
            return (dist.metadata["Name"], dist.version)
        except Exception:  # noqa: BLE001
            continue
    return None


def _fetch_latest_pypi_version(
    package: str,
    *,
    http_runner: Callable[[str, float], tuple[int, bytes]] | None = None,
) -> str | None:
    """Return ``info.version`` of ``package`` from PyPI JSON, or None.

    Fail-open: any HTTP / JSON / network failure returns ``None``.
    """
    runner = http_runner or _default_http_runner
    url = _PYPI_JSON_URL.format(name=package)
    try:
        status, body = runner(url, _HTTP_TIMEOUT_S)
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    if status != 200:
        return None
    try:
        doc = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    info = doc.get("info")
    if not isinstance(info, dict):
        return None
    version = info.get("version")
    return version if isinstance(version, str) else None


def _version_tuple(text: str) -> tuple[int, ...]:
    """Lossy SemVer-ish parse — leading numeric components."""
    import re

    parts: list[int] = []
    for chunk in re.split(r"[^0-9]+", text or ""):
        if not chunk:
            continue
        try:
            parts.append(int(chunk))
        except ValueError:
            break
    return tuple(parts)


def _is_drifted(installed: str, latest: str) -> bool:
    """Return True when ``installed`` < ``latest`` per the tuple parse."""
    a = _version_tuple(installed)
    b = _version_tuple(latest)
    if not a or not b:
        return False
    return a < b


# ---------------------------------------------------------------------------
# Per-service check
# ---------------------------------------------------------------------------


def check_one_service(
    *,
    job,
    apply: bool,
    http_runner: Callable[[str, float], tuple[int, bytes]] | None = None,
    pip_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    systemctl_runner: Callable[..., subprocess.CompletedProcess] | None = None,
    metadata_lookup=None,
    which: Callable[[str], str | None] = shutil.which,
) -> ServiceOutcome:
    """Check one JobSpec for drift; return a structured outcome."""
    binary = _extract_binary(job.command)
    if binary is None:
        return ServiceOutcome(
            job_name=job.name,
            binary=None,
            package=None,
            installed_version=None,
            latest_version=None,
            drift=False,
            action="skipped",
            detail="JobSpec.command has no first token",
        )

    owner = _resolve_owning_distribution(
        binary, metadata_lookup=metadata_lookup or metadata.entry_points
    )
    if owner is None:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=None,
            installed_version=None,
            latest_version=None,
            drift=False,
            action="skipped",
            detail=(
                "no console-script entry maps to "
                f"{_binary_basename(binary)!r} (not pip-installed?)"
            ),
        )

    package, installed = owner
    latest = _fetch_latest_pypi_version(package, http_runner=http_runner)
    if latest is None:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=None,
            drift=False,
            action="skipped",
            detail="could not fetch latest PyPI version (network / JSON)",
        )

    drifted = _is_drifted(installed, latest)
    if not drifted:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=False,
            action="ok",
        )

    if not apply:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="would-update",
            detail=f"installed={installed} latest={latest} (dry-run)",
        )

    pip = pip_runner or _default_pip_runner
    sysctl = systemctl_runner or _default_systemctl_runner

    if which("pip") is None:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="error",
            detail="pip not on PATH; cannot apply update",
        )

    try:
        r = pip(["install", "-U", package])
    except Exception as exc:  # noqa: BLE001
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="error",
            detail=f"pip install -U {package} raised: {exc}",
        )
    if r.returncode != 0:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="error",
            detail=f"pip install -U {package} rc={r.returncode}: "
            f"{(r.stderr or r.stdout).strip()[:200]}",
        )

    from ..jobs._systemd import systemd_unit_name

    unit = systemd_unit_name(job)
    try:
        rr = sysctl(["restart", unit])
    except Exception as exc:  # noqa: BLE001
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="error",
            detail=f"systemctl restart {unit} raised: {exc}",
        )
    if rr.returncode != 0:
        return ServiceOutcome(
            job_name=job.name,
            binary=binary,
            package=package,
            installed_version=installed,
            latest_version=latest,
            drift=True,
            action="error",
            detail=f"systemctl restart {unit} rc={rr.returncode}: "
            f"{(rr.stderr or rr.stdout).strip()[:200]}",
        )

    return ServiceOutcome(
        job_name=job.name,
        binary=binary,
        package=package,
        installed_version=installed,
        latest_version=latest,
        drift=True,
        action="updated",
        detail=f"{installed} -> {latest} + restarted {unit}",
    )


# ---------------------------------------------------------------------------
# Top-level body
# ---------------------------------------------------------------------------


def _append_audit_line(log_path: Path, line: str) -> None:
    """Append one structured audit line. Best-effort write."""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")
    except OSError:
        pass


def run_once(
    *,
    apply: bool = False,
    jobs_provider=None,
    log_path: Path | None = None,
    http_runner: Callable[[str, float], tuple[int, bytes]] | None = None,
    pip_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    systemctl_runner: Callable[..., subprocess.CompletedProcess] | None = None,
    metadata_lookup=None,
    which: Callable[[str], str | None] = shutil.which,
    now: Callable[[], float] | None = None,
) -> DeployFreshnessResult:
    """One deploy-freshness sweep across every kind=service+timer JobSpec."""
    log = (log_path or _default_log_path()).expanduser()
    import time

    clock = now or time.time
    timestamp = datetime.fromtimestamp(clock(), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%MZ"
    )

    if jobs_provider is None:
        from ..jobs import jobs_of_kind

        def jobs_provider():  # noqa: E306
            return list(jobs_of_kind("service")) + list(jobs_of_kind("timer"))

    try:
        services = jobs_provider()
    except Exception as exc:  # noqa: BLE001
        msg = f"discover_jobs failed: {exc.__class__.__name__}: {exc}"
        _append_audit_line(log, f"[deploy-freshness {timestamp}] ERROR: {msg}")
        return DeployFreshnessResult(log_path=str(log), error=msg)

    outcomes: list[ServiceOutcome] = []
    drift = 0
    updated = 0
    errors = 0
    for job in services:
        outcome = check_one_service(
            job=job,
            apply=apply,
            http_runner=http_runner,
            pip_runner=pip_runner,
            systemctl_runner=systemctl_runner,
            metadata_lookup=metadata_lookup,
            which=which,
        )
        outcomes.append(outcome)
        if outcome.drift:
            drift += 1
        if outcome.action == "updated":
            updated += 1
        if outcome.action == "error":
            errors += 1
        line = (
            f"[deploy-freshness {timestamp}] job={outcome.job_name} "
            f"pkg={outcome.package} installed={outcome.installed_version} "
            f"latest={outcome.latest_version} action={outcome.action}"
        )
        if outcome.detail:
            line += f" detail={outcome.detail!r}"
        _append_audit_line(log, line)

    summary = (
        f"[deploy-freshness {timestamp}] SUMMARY checked={len(services)} "
        f"drift={drift} updated={updated} errors={errors} apply={apply}"
    )
    _append_audit_line(log, summary)

    return DeployFreshnessResult(
        log_path=str(log),
        services_checked=len(services),
        drift_count=drift,
        updated_count=updated,
        error_count=errors,
        outcomes=tuple(outcomes),
    )


# EOF
