#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron list`` — enumerate managed cron lines."""

from __future__ import annotations

import json

import click

from . import _crontab
from ._jobs import JOB_REGISTRY, list_jobs
from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand


def _classify(line, spec):
    """Return (status, color) for an installed managed line vs. registry."""
    if spec is None:
        return "unknown", "yellow"
    if spec.schedule == line.schedule and spec.command == line.command:
        return "ok", "green"
    return "drifted", "yellow"


def register(group: click.Group) -> None:
    @group.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List managed cron jobs.",
            description=(
                "Shows two views: 'registry' — every job known to "
                "scitex-dev (whether installed or not), with its "
                "declared schedule + description; 'installed' — every "
                "`# scitex-dev cron: <name>` line currently present in "
                "the user's crontab, with status (matches registry, "
                "drifted, or unknown).",
            ),
            examples=(
                Example("{prog} cron list", "Registry + installed status."),
                Example("{prog} cron list --registry-only", "Registry only."),
                Example("{prog} cron list --json", "Structured JSON output."),
            ),
        ),
    )
    @click.option(
        "--registry-only",
        is_flag=True,
        default=False,
        help="Show registry entries only — skip reading the crontab.",
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Output as structured JSON.",
    )
    def list_cmd(registry_only: bool, as_json: bool) -> None:
        registry = [
            {
                "name": s.name,
                "schedule": s.schedule,
                "command": s.command,
                "description": s.description,
            }
            for s in list_jobs()
        ]
        installed: list[dict] = []
        unreadable_reason: str | None = None
        if not registry_only:
            try:
                read = _crontab.read_crontab_state()
            except RuntimeError as exc:
                raise click.ClickException(str(exc)) from exc
            if not read.readable:
                unreadable_reason = read.reason or "crontab unavailable"
            for line in _crontab.parse_managed(read.text):
                spec = JOB_REGISTRY.get(line.name)
                status, _color = _classify(line, spec)
                installed.append(
                    {
                        "name": line.name,
                        "schedule": line.schedule,
                        "command": line.command,
                        "status": status,
                    }
                )

        if as_json:
            # `installed` is null — NOT [] — when the crontab could not be
            # read, so a machine consumer counting it cannot mistake
            # "could not look" for "looked, found zero".
            payload = {
                "registry": registry,
                "installed": None if unreadable_reason else installed,
                "installed_state": "unknown" if unreadable_reason else "read",
                "installed_unavailable_reason": unreadable_reason,
            }
            if registry_only:
                payload.pop("installed")
                payload.pop("installed_state")
                payload.pop("installed_unavailable_reason")
            click.echo(json.dumps(payload, indent=2))
            return

        click.secho("registry:", bold=True)
        for spec_dict in registry:
            click.echo(
                f"  {spec_dict['name']:16s} {spec_dict['schedule']:14s} "
                f"{spec_dict['description']}"
            )

        if registry_only:
            return

        click.echo("")
        if unreadable_reason:
            click.secho(
                f"installed: UNKNOWN ({unreadable_reason})",
                bold=True,
                fg="yellow",
            )
            click.echo(
                "  Could not read this host's crontab, so nothing is known "
                "about what is installed."
            )
            click.echo(
                "  This is NOT 'zero jobs installed' — the jobs may well be "
                "running elsewhere (e.g. on the host, not in this container)."
            )
            return

        click.secho(f"installed ({len(installed)}):", bold=True)
        if not installed:
            click.echo("  (none)")
            return

        for entry in installed:
            color = "green" if entry["status"] == "ok" else "yellow"
            click.secho(
                f"  {entry['name']:16s} {entry['schedule']:14s} [{entry['status']}]",
                fg=color,
            )
            if entry["status"] == "drifted":
                spec = JOB_REGISTRY.get(entry["name"])
                click.echo(f"    crontab cmd:  {entry['command']}")
                click.echo(f"    registry cmd: {spec.command if spec else '(none)'}")


# EOF
