#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/versioning/_sources.py

"""The evidence seams: where the facts come from.

Every fact the checks reason about arrives through :class:`Sources`. Two
implementations, the same interface:

* :class:`LiveSources` — the real thing. PyPI over HTTPS, ``git tag``,
  ``gh run list``, ``importlib.metadata`` via scitex-dev's content-verified
  ``_install_probe``, editable ahead/behind via ``check_editable_drift``,
  ``systemctl show``.
* :class:`StaticSources` — the same interface, handed data captured from
  those real systems. This is what the tests drive: no mocks, no
  monkeypatching, no network — a real object with a real implementation, fed
  real recorded evidence (including the actual PyPI release list and the
  actual GitHub run conclusions from a recorded incident).

**Every method returns ``None`` when it cannot get a real answer.** That
``None`` is the only way UNKNOWN reaches the verdict layer, and it is why
this alarm cannot become the next false-green: a source that cannot see says
so, instead of returning an empty list that reads like "nothing wrong".

TIMEOUTS are deliberately generous (20-30 s). A tight timeout on a loaded box
does not "fail fast" — it manufactures an UNKNOWN out of a machine that was
merely busy. None of this is on an interactive path; the refresher runs off
the hot path and nobody is waiting on it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from ._config import VersioningConfig

__all__ = ["LiveSources", "Sources", "StaticSources"]

# Generous on purpose: a busy host must not be mistaken for a broken one.
_HTTP_TIMEOUT_S = 30
_CMD_TIMEOUT_S = 30


class Sources(Protocol):
    """The facts a currency verdict needs. ``None`` always means UNKNOWN."""

    def install_kind(self) -> str | None:
        """``wheel`` / ``editable`` / ``orphaned`` / ``absent`` /
        ``unmanaged``, or ``None`` if it cannot be told."""

    def effective_version(self) -> str | None:
        """The version actually RUNNING — content-verified, never the raw
        fossil metadata."""

    def metadata_version(self) -> str | None:
        """The RAW ``importlib.metadata`` claim — which may be a fossil.
        Reported so a drift between it and the code can be named."""

    def module_origin(self) -> str | None:
        """Filesystem path the module actually loaded from (``__file__`` or
        the editable source root). Names WHOSE install answered."""

    def executable(self) -> str:
        """The interpreter running the check (``sys.executable``)."""

    def pypi_latest(self) -> str | None:
        """PyPI's own idea of the newest release."""

    def pypi_versions(self) -> set[str] | None:
        """Every version PyPI has ever published — the only truth about what
        shipped, not the tag or the GitHub release."""

    def git_tags(self) -> list[str] | None:
        """Every ``v*`` release tag."""

    def editable_ahead_behind(self) -> tuple[int, int] | None:
        """``(ahead, behind)`` of the editable working tree vs its latest
        tag. ``None`` for wheels / no checkout."""

    def release_runs(self) -> list[dict] | None:
        """Recent release-workflow runs, newest first."""

    def daemon_started_at(self) -> float | None:
        """When the long-lived daemon began executing (epoch seconds)."""

    def installed_at(self) -> float | None:
        """When the installed package was last written (epoch seconds)."""


class LiveSources:
    """Real evidence, from the real systems, parameterised by config."""

    def __init__(self, config: VersioningConfig):
        self._cfg = config
        self._probe = None  # cached InstallProbe
        self._pypi: dict | None | object = _UNSET

    # -- install identity (content-verified) -----------------------------
    def _install_probe(self):
        if self._probe is None:
            from .._release._install_probe import probe_install

            self._probe = probe_install(self._cfg.dist, self._cfg.module)
        return self._probe

    def install_kind(self) -> str | None:
        return self._install_probe().kind or None

    def effective_version(self) -> str | None:
        return self._install_probe().effective_version

    def metadata_version(self) -> str | None:
        return self._install_probe().metadata_version

    def module_origin(self) -> str | None:
        p = self._install_probe()
        return p.source_root or p.module_path

    def executable(self) -> str:
        return sys.executable

    # -- PyPI ------------------------------------------------------------
    def _pypi_json(self) -> dict | None:
        if self._pypi is _UNSET:
            self._pypi = self._fetch_pypi()
        return self._pypi  # type: ignore[return-value]

    def _fetch_pypi(self) -> dict | None:
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(
                self._cfg.pypi_json_url, timeout=_HTTP_TIMEOUT_S
            ) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            # offline/slow/garbled PyPI is UNKNOWN, never "fine"
            return None

    def pypi_latest(self) -> str | None:
        data = self._pypi_json()
        if not data:
            return None
        return (data.get("info") or {}).get("version")

    def pypi_versions(self) -> set[str] | None:
        data = self._pypi_json()
        if not data:
            return None
        releases = data.get("releases")
        if not isinstance(releases, dict):
            return None
        # A version with an empty file list was yanked/never uploaded; it is
        # NOT a shipped release, and counting it would let a ghost masquerade
        # as published.
        return {v for v, files in releases.items() if files}

    # -- the repo --------------------------------------------------------
    def repo_root(self) -> Path | None:
        if self._cfg.repo_root is not None:
            return self._cfg.repo_root
        origin = self._install_probe().source_root
        return Path(origin) if origin else None

    def git_tags(self) -> list[str] | None:
        root = self.repo_root()
        if root is None:
            return None
        out = _run(["git", "-C", str(root), "tag", "-l", "v*"])
        if out is None:
            return None
        return [line.strip() for line in out.splitlines() if line.strip()]

    def editable_ahead_behind(self) -> tuple[int, int] | None:
        if self._install_probe().kind != "editable":
            return None
        from ._editable import editable_source_dir, editable_ahead_behind

        src = editable_source_dir(self._cfg.dist)
        if src is None:
            return None
        return editable_ahead_behind(src)

    def release_runs(self) -> list[dict] | None:
        if not self._cfg.release_workflow:
            return None
        out = _run(
            [
                "gh", "run", "list",
                "--workflow", self._cfg.release_workflow,
                "--limit", "10",
                "--json", "conclusion,status,headBranch,createdAt,url",
            ],
            cwd=self.repo_root(),
        )
        if out is None:
            return None
        try:
            runs = json.loads(out)
        except ValueError:
            return None
        return runs if isinstance(runs, list) else None

    # -- the running daemon ----------------------------------------------
    def daemon_started_at(self) -> float | None:
        if not self._cfg.systemd_unit:
            return None
        out = _run(
            [
                "systemctl", "--user", "show", self._cfg.systemd_unit,
                "-p", "ExecMainStartTimestampMonotonic",
                "--value",
            ]
        )
        if out is None:
            return None
        return _parse_systemd_monotonic(out)

    def installed_at(self) -> float | None:
        from importlib.metadata import PackageNotFoundError, distribution

        try:
            dist = distribution(self._cfg.dist)
        except PackageNotFoundError:
            return None
        base = getattr(dist, "_path", None)
        if isinstance(base, Path) and base.exists():
            try:
                return base.stat().st_mtime
            except OSError:
                return None
        return None


class StaticSources:
    """The same interface, fed real recorded evidence. For tests.

    Not a mock: a genuine implementation of :class:`Sources` whose backing
    store happens to be a dict instead of a network. Tests hand it the actual
    bytes the real systems returned, so the verdict logic is exercised
    against reality without ever touching reality.
    """

    def __init__(
        self,
        *,
        install_kind=None,
        effective_version=None,
        metadata_version=None,
        module_origin=None,
        executable="/test/python",
        pypi_latest=None,
        pypi_versions=None,
        git_tags=None,
        editable_ahead_behind=None,
        release_runs=None,
        daemon_started_at=None,
        installed_at=None,
    ):
        self._install_kind = install_kind
        self._effective_version = effective_version
        self._metadata_version = metadata_version
        self._module_origin = module_origin
        self._executable = executable
        self._pypi_latest = pypi_latest
        self._pypi_versions = pypi_versions
        self._git_tags = git_tags
        self._editable_ahead_behind = editable_ahead_behind
        self._release_runs = release_runs
        self._daemon_started_at = daemon_started_at
        self._installed_at = installed_at

    def install_kind(self):
        return self._install_kind

    def effective_version(self):
        return self._effective_version

    def metadata_version(self):
        return self._metadata_version

    def module_origin(self):
        return self._module_origin

    def executable(self):
        return self._executable

    def pypi_latest(self):
        return self._pypi_latest

    def pypi_versions(self):
        return set(self._pypi_versions) if self._pypi_versions is not None else None

    def git_tags(self):
        return list(self._git_tags) if self._git_tags is not None else None

    def editable_ahead_behind(self):
        return self._editable_ahead_behind

    def release_runs(self):
        return list(self._release_runs) if self._release_runs is not None else None

    def daemon_started_at(self):
        return self._daemon_started_at

    def installed_at(self):
        return self._installed_at


class _Unset:
    pass


_UNSET = _Unset()


def _run(argv: list[str], cwd: Path | None = None) -> str | None:
    """Run a command; ``None`` on any failure. Never raises, never hangs."""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT_S,
            cwd=str(cwd) if cwd else None,
        )
    except (OSError, subprocess.SubprocessError):
        # missing binary / timeout is UNKNOWN, never "fine"
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _parse_systemd_monotonic(raw: str) -> float | None:
    """``ExecMainStartTimestampMonotonic`` (usec) -> wall-clock epoch seconds.

    ``0`` means the unit exists but has never run -> nothing is running ->
    UNKNOWN, not stale. Translated via ``/proc/uptime`` to avoid a date
    parser.
    """
    line = raw.strip().splitlines()[0].strip() if raw.strip() else ""
    try:
        monotonic_usec = int(line)
    except ValueError:
        return None
    if monotonic_usec <= 0:
        return None
    try:
        with open("/proc/uptime", encoding="utf-8") as fh:
            uptime_s = float(fh.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    import time as _time

    boot_epoch = _time.time() - uptime_s
    return boot_epoch + (monotonic_usec / 1_000_000.0)


# EOF
