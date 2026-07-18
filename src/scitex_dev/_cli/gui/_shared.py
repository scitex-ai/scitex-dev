#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers shared by the terminal surfaces mounted on the `gui` group.

Package-selection parsing and the ssh streaming renderer used by
`gui list --host`. Kept apart from the command modules so each of those
stays a thin, readable Click layer.
"""

from __future__ import annotations

import click

__all__ = ["render_remote", "resolve_packages", "shquote"]


def shquote(s: str) -> str:
    """POSIX shell single-quote a string for embedding in `bash -lc '...'`."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def resolve_packages(package: tuple[str, ...]) -> list[str] | None:
    """`-p` accepts repeats, comma-separated values, and the literal `all`.

    Mirrors `audit-all`'s argument style. Returns None for "every
    package" — both the `all` literal and the no-flag default.
    """
    raw: list[str] = []
    for entry in package:
        raw.extend(p.strip() for p in entry.split(",") if p.strip())
    if "all" in raw or not raw:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for p in raw:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def render_remote(
    *,
    host: str,
    verbosity: int,
    packages: list,
    jobs: int,
    with_tests: str,
    as_json: bool,
) -> None:
    """Stream `gui list --json-stream` from `host`; render live.

    Uses ``--json-stream`` (one JSON snapshot per line, emitted after
    each enricher batch completes) so the local view fills in
    incrementally — same UX as a local `gui list`. Without this, ssh
    blocks for the full ~40s while the remote runs every enricher.

    If ``as_json`` is requested, the last (= most complete) snapshot is
    forwarded verbatim.
    """
    import json as _json
    import subprocess

    from rich.console import Console
    from rich.live import Live

    from ..ecosystem._dashboard._render import render_table
    from ..ecosystem._dashboard._state import PackageState

    remote_cmd_parts = [
        "scitex-dev",
        "gui",
        "list",
        "--json-stream",
        "-j",
        str(jobs),
        "--with-tests",
        with_tests,
    ]
    if verbosity > 1:
        remote_cmd_parts.append("-" + "v" * (verbosity - 1))
    for p in packages:
        remote_cmd_parts.extend(["-p", p])
    remote_cmd = " ".join(remote_cmd_parts)
    # `bash -lc` so the user's PATH (incl. ~/.env-*/bin) is sourced.
    # `-o BatchMode=yes` avoids interactive password prompts hanging.
    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        host,
        f"bash -lc {shquote(remote_cmd)}",
    ]
    try:
        proc = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as e:
        raise click.ClickException(f"ssh to {host} failed: {e}")

    last_rows: list = []
    console = Console()

    def _states() -> list:
        return [PackageState.from_dict(r) for r in last_rows]

    if as_json:
        # No live render — just drain to EOF and forward the final snapshot.
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line.startswith("["):
                continue
            try:
                last_rows = _json.loads(line)
            except _json.JSONDecodeError:
                continue
        proc.wait(timeout=10)
        click.echo(_json.dumps(last_rows, indent=2, default=str))
        return

    with Live(
        render_table([], verbosity=verbosity, host=host),
        console=console,
        refresh_per_second=2,
        transient=False,
        screen=True,
    ) as live:
        live.console.print(
            f"[dim]streaming from {host} over ssh — first snapshot lands "
            f"after the cheap basic-gather batch (~1-2s); full enrichment "
            f"~30-60s on a cold cache[/dim]"
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line.startswith("["):
                continue
            try:
                last_rows = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            live.update(render_table(_states(), verbosity=verbosity, host=host))
        live.update(render_table(_states(), verbosity=verbosity, host=host))

    try:
        rc = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        rc = -1
    if rc != 0 and not last_rows:
        err = (proc.stderr.read() if proc.stderr else "")[:2000]
        raise click.ClickException(
            f"remote `gui list` on {host} exited {rc}:\n--- stderr ---\n{err}"
        )

    console.print(render_table(_states(), verbosity=verbosity, host=host))


# EOF
