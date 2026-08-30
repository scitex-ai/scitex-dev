#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The two-dimensional pass: every package, on every host.

scitex-dev is the right home for this because it already knows BOTH
axes — :mod:`scitex_dev._ecosystem` holds the package registry and
:mod:`scitex_dev.hosts` holds the host registry — so neither list has to
be re-derived or hardcoded here.

HOW THE HOST AXIS IS CROSSED, AND WHY IT IS CROSSED THAT WAY
------------------------------------------------------------
There is no ``(host, package) -> checkout path`` helper anywhere in
scitex-dev, and inventing one would mean this module deciding where
another machine keeps its code. ``HostRecord`` carries ``scitex_root``
(the config/state directory) and no source root at all; the four places
that need a remote path today each re-derive ``~/proj/<dir>`` by hand
against a DIFFERENT, older host abstraction.

So the fan-out does not compute remote paths. It re-invokes THIS VERB on
the remote host and lets that host answer from its own registry. The
remote leg is suppressed on every fan-out target for the reason in
:func:`._repo.sweep_remote`: remote refs are shared, so one pass serves
the fleet and seven passes are six redundant failures.

WHAT THE HOST REGISTRY DOES NOT GIVE US, STATED RATHER THAN PAPERED OVER
------------------------------------------------------------------------
``list_hosts()`` returns every row in ``hosts.yaml`` and has no
liveness, no enabled flag and no per-host retirement field — retirement
is recorded per SSH ALIAS in :mod:`scitex_dev.hosts._retired` and only
warns. A row with no ``ssh_alias`` has no recorded route, which is NOT
the same as being local. This module therefore skips: the local host,
rows with no alias, and aliases with a declared successor — and reports
each skip with its reason instead of silently shortening the fleet.
"""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

from ._model import DEFAULT_MAX_AGE_HOURS, PROTECTED_EXACT, RepoResult, SweepOutcome
from ._repo import sweep_repo

#: How long one host's whole pass may take before the fan-out gives up.
#: Generous because the biggest measured checkout set is 80 repositories
#: and each one fetches; a timeout is reported as a skip, never retried.
REMOTE_TIMEOUT_SEC = 1_800


def registry_repos(
    packages: list[str] | None = None,
    *,
    registry: dict | None = None,
) -> list[tuple[str, Path]]:
    """``(package, checkout path)`` for every registered, non-archived package.

    Reads :data:`scitex_dev._ecosystem.ECOSYSTEM` rather than walking a
    directory, so the sweep's scope is the SAME curated list every other
    ecosystem verb uses. Paths that do not exist on this host are
    dropped here: a package registered fleet-wide but not checked out
    locally is not this host's business.

    ``registry`` names the collaborator explicitly. The real one is a
    living list of ~70 packages that changes weekly, so a test asserting
    anything about its CONTENTS would be asserting somebody else's data;
    passing a small one in lets a test pin the CONSUMPTION — which is
    the part this module owns — without rewriting production internals.
    """
    if registry is None:
        from .._ecosystem import ECOSYSTEM

        registry = ECOSYSTEM
    wanted = set(packages) if packages else None
    found: list[tuple[str, Path]] = []
    for name, info in registry.items():
        if wanted is not None and name not in wanted:
            continue
        if info.get("archived"):
            continue
        raw = info.get("local_path") or f"~/proj/{name}"
        path = Path(raw).expanduser()
        if (path / ".git").exists():
            found.append((name, path))
    return found


def fleet_hosts() -> tuple[list[str], list[tuple[str, str]]]:
    """``(ssh aliases to visit, [(host, why it was skipped)])``.

    The skip list is returned rather than swallowed. A fan-out that
    silently visits four of nine hosts reports the same "all clean" as
    one that visited all nine.
    """
    from ..hosts import is_local, list_hosts
    from ..hosts._retired import successor_for

    aliases: list[str] = []
    skipped: list[tuple[str, str]] = []
    for host in list_hosts():
        if is_local(host):
            skipped.append((host.name, "local host — swept directly"))
            continue
        if not host.ssh_alias:
            skipped.append((host.name, "no ssh_alias recorded"))
            continue
        successor = successor_for(host.ssh_alias)
        if successor:
            skipped.append((host.name, f"alias retired in favour of {successor}"))
            continue
        aliases.append(host.ssh_alias)
    return aliases, skipped


def _shquote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def remote_argv(
    *, execute: bool, max_age_hours: float, packages: list[str] | None
) -> list[str]:
    """The verb this fan-out runs on a remote host.

    ``--no-remote`` is unconditional: the remote branch leg belongs to
    exactly one pass in the whole fleet, and this is not it.
    """
    argv = ["scitex-dev", "ecosystem", "branch-hygiene", "--json", "--no-remote"]
    if execute:
        argv.append("--execute")
    argv += ["--max-age-hours", str(max_age_hours)]
    for name in packages or []:
        argv += ["--package", name]
    return argv


def run_on_host(
    alias: str, argv: list[str], *, timeout: int = REMOTE_TIMEOUT_SEC
) -> tuple[int, str, str]:
    """``ssh <alias> bash -lc '<argv>'`` -> ``(rc, stdout, stderr)``.

    ``bash -lc`` so the remote login PATH resolves ``scitex-dev``, and
    ``BatchMode=yes`` so an unreachable host fails in seconds instead of
    blocking a scheduled job on a password prompt nobody will answer.
    """
    command = " ".join(argv)
    try:
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", alias, f"bash -lc {_shquote(command)}"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return 127, "", f"ssh not found: {exc}"
    except subprocess.TimeoutExpired:
        return 124, "", f"ssh to {alias} timed out after {timeout}s"
    return proc.returncode, proc.stdout, proc.stderr


def _host_results(alias: str, stdout: str, stderr: str) -> list[RepoResult]:
    """Turn a remote payload into rows, or ONE row saying it did not parse."""
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        detail = (stderr or stdout or "no output").strip().splitlines()
        return [
            RepoResult(
                package=f"@{alias}",
                repo=alias,
                error=f"unreadable reply: {detail[-1] if detail else 'empty'}",
            )
        ]
    rows: list[RepoResult] = []
    for raw in payload.get("results", []):
        rows.append(
            RepoResult(
                package=raw.get("package", ""),
                repo=f"{alias}:{raw.get('repo', '')}",
                error=raw.get("error", ""),
            )
        )
    return rows


def sweep_local_host(
    *,
    execute: bool = False,
    do_local: bool = True,
    do_remote: bool = False,
    packages: list[str] | None = None,
    now: float | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    protected: frozenset[str] = PROTECTED_EXACT,
) -> SweepOutcome:
    """Sweep every registered checkout that exists on THIS machine."""
    results = tuple(
        sweep_repo(
            path,
            package=name,
            execute=execute,
            do_local=do_local,
            do_remote=do_remote,
            now=now,
            max_age_hours=max_age_hours,
            protected=protected,
        )
        for name, path in registry_repos(packages)
    )
    return SweepOutcome(
        results=results,
        executed=execute,
        remote_pass=do_remote,
        host=socket.gethostname(),
    )


def fan_out(
    *,
    execute: bool = False,
    packages: list[str] | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> tuple[list[RepoResult], list[tuple[str, str]]]:
    """Run the local leg of this verb on every reachable registered host.

    Returns ``(rows, skips)``. Only per-repository ERRORS survive the
    round trip as rows: the full per-branch detail belongs in the remote
    host's own log, and folding several thousand verdicts from seven
    hosts into one report makes the one line that matters unreadable.
    """
    aliases, skipped = fleet_hosts()
    argv = remote_argv(
        execute=execute, max_age_hours=max_age_hours, packages=packages
    )
    rows: list[RepoResult] = []
    for alias in aliases:
        code, stdout, stderr = run_on_host(alias, argv)
        if code in (124, 127) or (code and not stdout.strip()):
            skipped.append((alias, (stderr or f"exit {code}").strip()))
            continue
        rows.extend(row for row in _host_results(alias, stdout, stderr) if row.error)
    return rows, skipped


# EOF
