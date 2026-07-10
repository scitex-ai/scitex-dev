#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron remove <name>`` — strip a managed cron line."""

from __future__ import annotations

import click

from . import _crontab
from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(group: click.Group) -> None:
    @group.command(
        "remove",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Remove the managed cron line for NAME.",
            description=(
                "Operates only on lines tagged with the marker `# "
                "scitex-dev cron: <name>`. Every other line in the "
                "crontab is preserved verbatim.",
            ),
            examples=(
                Example("{prog} cron remove ci-watch --dry-run", "Preview the removal."),
                Example("{prog} cron remove ci-watch --yes", "Remove the line."),
            ),
        ),
    )
    @click.argument("name")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Report how many lines would be removed; do not write.",
    )
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help="Confirm. Required when not --dry-run.",
    )
    def remove_cmd(name: str, dry_run: bool, yes: bool) -> None:
        try:
            current = _crontab.read_crontab()
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        new, removed = _crontab.remove_managed(current, name)

        if dry_run:
            click.echo(f"would remove {removed} managed line(s) for {name!r}.")
            return

        if removed == 0:
            click.echo(f"no managed line found for {name!r}; nothing to do.")
            return

        if not yes:
            click.echo(
                f"would remove {removed} managed line(s) for {name!r}. "
                "Re-run with --yes to apply.",
                err=True,
            )
            raise SystemExit(2)

        try:
            _crontab.write_crontab(new)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        click.echo(f"removed {removed} managed line(s) for {name!r}.")


# EOF
