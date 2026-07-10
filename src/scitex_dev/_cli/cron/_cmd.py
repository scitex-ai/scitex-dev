#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron`` Click group + subcommand registration."""

from __future__ import annotations

import click

from . import install, list as list_mod, remove, run, status
from ..._ecosystem.help_spec import CliHelp, Example, SpecGroup


def register_cron_commands(main_group: click.Group) -> click.Group:
    """Register ``scitex-dev cron`` on the given main group."""

    @main_group.group(
        "cron",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Ecosystem-wide cron management.",
            description=(
                "Manages a registry of named cron jobs across the SciTeX "
                "ecosystem. Each managed crontab line is tagged with "
                "`# scitex-dev cron: <name>` so install / remove "
                "operations target only that line and never disturb "
                "unrelated entries. First registered job: `ci-watch` — "
                "polls each sac agent's owned repo for CI red on develop "
                "and dispatches a fix-forward A2A turn to the "
                "responsible agent when failures are detected.\n\n"
                "Verbs: list (show registry + installed lines), install "
                "(idempotent), remove (strip the named job), status "
                "(last-run / next-run hints), exec (execute a job's "
                "body, used by cron itself).",
            ),
            examples=(Example("{prog} cron list", "Show registered jobs."),),
        ),
    )
    @click.pass_context
    def cron(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    install.register(cron)
    list_mod.register(cron)
    remove.register(cron)
    status.register(cron)
    run.register(cron)
    return cron


# EOF
