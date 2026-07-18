#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron status`` — last-run / next-run for managed jobs."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import click

from . import _crontab
from ._job_commands import log_path_for
from ._jobs import JOB_REGISTRY
from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand


def _legacy_log_path(name: str) -> Path:
    """The pre-2026-07-19 log location: ``~/.scitex/dev/logs/cron-<name>.log``.

    Kept ONLY as a read fallback. Existing logs are deliberately not
    moved by the cleanup, so a job that has not ticked since the change
    still reports a real last-run instead of "(no log yet)".
    """
    return Path.home() / ".scitex" / "dev" / "logs" / f"cron-{name}.log"


def _last_run_from_log(name: str) -> str:
    """Best-effort last-run timestamp from the job's log file.

    Each job's log is owned by ``cron exec`` and lives under
    ``$HOME/.scitex/<pkg>/runtime/logs/`` (see ``_job_commands`` /
    ``jobs._logsink``). We report the file's mtime — exact enough for an
    operator to see "the loop is alive" without parsing the log body,
    and we take the NEWER of the new and legacy paths so the reading
    stays honest across the transition.
    """
    candidates = [p for p in (log_path_for(name), _legacy_log_path(name)) if p.exists()]
    if not candidates:
        return "(no log yet)"
    mtime = max(p.stat().st_mtime for p in candidates)
    return _dt.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")


def register(group: click.Group) -> None:
    @group.command(
        "status",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Show last-run / next-run hints for every managed cron job.",
            description=(
                "Reports per-job: installed? (line is present in "
                "`crontab -l`), schedule (declared vs. installed, "
                "flagged if they drift), last-run (mtime of "
                "`$HOME/.scitex/<pkg>/runtime/logs/<slug>.log`, falling "
                "back to the pre-cleanup `~/.scitex/dev/logs/` path), "
                "next-run (raw schedule, operator interprets).",
            ),
            examples=(
                Example("{prog} cron status", "Human-readable status table."),
                Example("{prog} cron status --json", "Structured JSON output."),
            ),
        ),
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Output as structured JSON.",
    )
    def status_cmd(as_json: bool) -> None:
        try:
            current = _crontab.read_crontab()
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        managed = {m.name: m for m in _crontab.parse_managed(current)}

        rows: list[dict] = []
        for name in sorted(JOB_REGISTRY):
            spec = JOB_REGISTRY[name]
            line = managed.get(name)
            if line is None:
                installed = "no"
                schedule = spec.schedule
            elif line.schedule != spec.schedule or line.command != spec.command:
                installed = "drifted"
                schedule = f"{line.schedule} (was {spec.schedule})"
            else:
                installed = "yes"
                schedule = line.schedule
            rows.append(
                {
                    "name": name,
                    "installed": installed,
                    "schedule": schedule,
                    "last_run": _last_run_from_log(name),
                    "description": spec.description,
                }
            )

        unknown = [
            {"name": m.name, "raw": m.raw}
            for m in managed.values()
            if m.name not in JOB_REGISTRY
        ]

        if as_json:
            click.echo(json.dumps({"jobs": rows, "unknown": unknown}, indent=2))
            return

        click.secho(
            f"{'name':16s} {'installed':10s} {'schedule':14s} "
            f"{'last-run':25s} description",
            bold=True,
        )
        for r in rows:
            click.echo(
                f"{r['name']:16s} {r['installed']:10s} {r['schedule']:14s} "
                f"{r['last_run']:25s} {r['description']}"
            )

        if unknown:
            click.echo("")
            click.secho("unknown managed lines:", bold=True, fg="yellow")
            for u in unknown:
                click.echo(f"  {u['name']:16s} {u['raw']}")


# EOF
