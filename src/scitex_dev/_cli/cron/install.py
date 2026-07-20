#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron install <name>`` — materialise a managed job.

``--dry-run`` prints a unified DIFF of the current crontab against the
one that would be written, so the shape of the change is visible before
anything is applied. ``--all`` re-materialises every registered job in
one pass — the migration path for crontabs still carrying the old
inline-``mkdir``/redirect lines.

Only lines tagged ``# scitex-dev cron: <name>`` are ever touched; sac,
lead and every other agent's crontab entries are preserved verbatim by
``_crontab.upsert_managed``.
"""

from __future__ import annotations

import difflib

import click

from . import _crontab
from ._jobs import JOB_REGISTRY, get_job
from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand


def _crontab_diff(before: str, after: str) -> str:
    """Return a unified diff of the crontab before/after the write."""
    diff = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile="crontab (current)",
        tofile="crontab (after install)",
        lineterm="",
    )
    return "\n".join(diff)


def register(group: click.Group) -> None:
    @group.command(
        "install",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Install (or replace) the managed cron line for NAME.",
            description=(
                "Idempotent: a single line tagged `# scitex-dev cron: "
                "<name>` is managed in place — reinstall replaces it. "
                "Unrelated crontab lines (sac, lead, other agents) are "
                "preserved verbatim. `--dry-run` prints the unified diff "
                "of the crontab that would result, without touching it. "
                "`--all` re-materialises every registered job in one "
                "pass.",
            ),
            examples=(
                Example("{prog} cron install ci-watch --dry-run", "Preview the diff."),
                Example("{prog} cron install ci-watch --yes", "Install it."),
                Example(
                    "{prog} cron install --all --dry-run",
                    "Preview the whole managed set.",
                ),
                Example("{prog} cron install --all --yes", "Re-materialise them all."),
            ),
        ),
    )
    @click.argument("name", required=False)
    @click.option(
        "--all",
        "install_all",
        is_flag=True,
        default=False,
        help="Install every registered job instead of a single NAME.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print the unified crontab diff that would be applied; "
        "do not touch the crontab.",
    )
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help="Confirm. Required when not --dry-run.",
    )
    def install_cmd(
        name: str | None, install_all: bool, dry_run: bool, yes: bool
    ) -> None:
        if install_all and name:
            raise click.ClickException("pass either NAME or --all, not both.")
        if not install_all and not name:
            raise click.ClickException("NAME is required (or pass --all).")

        if install_all:
            specs = [JOB_REGISTRY[n] for n in sorted(JOB_REGISTRY)]
        else:
            try:
                specs = [get_job(name)]
            except KeyError as exc:
                raise click.ClickException(str(exc)) from exc

        try:
            current = _crontab.read_crontab()
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        new = current
        for spec in specs:
            new = _crontab.upsert_managed(new, spec.name, spec.schedule, spec.command)

        if dry_run:
            for spec in specs:
                click.echo(
                    _crontab.build_line(spec.name, spec.schedule, spec.command)
                )
            diff = _crontab_diff(current, new)
            click.echo("")
            if diff:
                click.echo(diff)
            else:
                click.echo("(no change — crontab already matches the registry)")
            return

        if not yes:
            click.echo("Refusing to write to crontab without --yes/-y.", err=True)
            raise SystemExit(2)

        try:
            _crontab.write_crontab(new)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc

        for spec in specs:
            click.echo(_crontab.build_line(spec.name, spec.schedule, spec.command))
        click.echo(f"installed ({len(specs)}).")


# EOF
