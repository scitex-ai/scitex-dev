#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``ecosystem dev service <verb>`` — the ``kind="service"`` CLI group.

One group per JobSpec KIND, matching the taxonomy the model already
enforces (``jobs._kinds.ALLOWED_KINDS`` is
``{"service", "timer", "cron"}``, and ``kind="systemd"`` raises). The old
``systemd`` group was organised by MECHANISM and fused ``service`` with
``timer``, so two kinds with genuinely different applicable fields shared
one surface while the model kept them apart.

That mismatch is not cosmetic. ``sac dev systemd list`` filtered
``kind="systemd"``, matched nothing, and printed "No sac systemd-kind
jobs." with exit 0 for weeks — hiding all four of sac's timers including
the fleet's sole OAuth refresher. A group that can only ever return zero
jobs is the failure this split exists to prevent.

Verbs, and why these
--------------------
``list`` ``status`` ``start`` ``stop`` ``restart`` ``install``
``uninstall``.

A verb meaningless for a kind is ABSENT here rather than present and
erroring: a service has no ``enable``/``disable`` distinct from
``install``/``uninstall`` (the unit's ``[Install] WantedBy=default.target``
IS its enablement), and no ``exec`` (a daemon is not a body you run once —
``ecosystem dev cron exec`` covers the run-once case for periodic work).
"""

from __future__ import annotations

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup
from . import _jobs_units as U

_KIND = "service"


def register(parent) -> None:
    """Mount the ``service`` kind group on ``parent`` (``ecosystem dev``)."""

    @parent.group(
        _KIND,
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Federated kind='service' daemons across the ecosystem.",
            description=(
                'Long-running user daemons declared as `kind="service"` '
                "JobSpecs by any package registered under the "
                "`scitex_dev.jobs` entry-point group. Backed by systemd "
                "`--user` units (Type=simple + Restart=). "
                "NOT AVAILABLE ON EVERY HOST: macOS uses launchd and the "
                "Synology/QNAP NAS boxes ship no systemd at all, so the "
                "verbs that need a user manager REFUSE with exit 3 and a "
                "named reason there rather than emitting a confusing "
                "systemctl error.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem dev service list",
                    "Every declared kind=service daemon.",
                ),
                Example(
                    "{prog} ecosystem dev service status sac.listen",
                    "Installed? active? supervised by what?",
                ),
            ),
        ),
    )
    @click.pass_context
    def service(ctx):
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    _add_list(service)
    _add_status(service)
    _add_lifecycle(service)
    _add_install(service)
    _add_uninstall(service)


def _add_list(group) -> None:
    @group.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List every discovered kind='service' job.",
            examples=(
                Example("{prog} ecosystem dev service list", "Human-readable."),
                Example(
                    "{prog} ecosystem dev service list --json",
                    "Structured JSON on stdout (diagnostics stay on stderr).",
                ),
            ),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def _list(as_json):
        U.emit_list(_KIND, as_json)


def _add_status(group) -> None:
    @group.command(
        "status",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Report install + supervision state for one service.",
            description=(
                "Read-only, and deliberately answerable on a host with no "
                "systemd: 'there is no unit and there never can be here' is "
                "the useful answer for a NAS, and refusing to answer would "
                "leave the operator no way to ask.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem dev service status sac.listen",
                    "Human-readable status.",
                ),
                Example(
                    "{prog} ecosystem dev service status sac.listen --json",
                    "Structured status.",
                ),
            ),
        ),
    )
    @click.argument("name")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def _status(name, as_json):
        U.do_status(_KIND, name=name, as_json=as_json)


def _add_lifecycle(group) -> None:
    """start / stop / restart — the verbs that only a daemon has."""

    for verb, blurb in (
        ("start", "Start the service unit now."),
        ("stop", "Stop the service unit now."),
        ("restart", "Restart the service unit now."),
    ):

        def _make(verb=verb, blurb=blurb):
            @group.command(
                verb,
                cls=SpecCommand,
                help_spec=CliHelp(
                    summary=f"{blurb} (systemctl --user {verb}).",
                    description=(
                        "MUTATING: needs --yes/-y. `restart` bounces a live "
                        "supervised daemon, so it must not happen because a "
                        "name was typed one word off. --dry-run prints the "
                        "systemctl command and works on ANY host. "
                        "Refuses with exit 3 and a named reason where no "
                        "`systemd --user` manager exists, so 'impossible "
                        "here' is distinguishable from 'tried and failed'.",
                    ),
                    examples=(
                        Example(
                            f"{{prog}} ecosystem dev service {verb} sac.listen --dry-run",
                            "Show the systemctl command; change nothing.",
                        ),
                        Example(
                            f"{{prog}} ecosystem dev service {verb} sac.listen --yes",
                            f"{verb.capitalize()} one declared daemon.",
                        ),
                    ),
                ),
            )
            @click.argument("name")
            @click.option(
                "--dry-run",
                is_flag=True,
                default=False,
                help="Print the systemctl command; do not run it.",
            )
            @click.option(
                "-y",
                "--yes",
                is_flag=True,
                default=False,
                help="Confirm. Required when not --dry-run.",
            )
            def _cmd(name, dry_run, yes, verb=verb):
                U.do_systemctl(_KIND, verb, name, dry_run=dry_run, yes=yes)

            return _cmd

        _make()


def _add_install(group) -> None:
    @group.command(
        "install",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Write the `<name>.service` unit for kind='service' jobs.",
            description=(
                "REFUSES when the job is ALREADY SUPERVISED — by a unit "
                "file, by a crontab line, or by a respawn loop. The scan is "
                "mechanism-blind on purpose: the head node currently runs "
                "`sac-listen.service` AND a `*/2 * * * *` crontab watchdog "
                "for the same process, and a check that looked only for a "
                "conflicting unit would have installed a third supervisor. "
                "Use --adopt to keep what is there (writes nothing) or "
                "--force to overwrite deliberately.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem dev service install --dry-run",
                    "Preview the unit text; works on any host.",
                ),
                Example(
                    "{prog} ecosystem dev service install --name sac.listen --adopt",
                    "Keep an existing hand-written supervisor.",
                ),
                Example(
                    "{prog} ecosystem dev service install --yes",
                    "Write units for every declared service.",
                ),
            ),
        ),
    )
    @click.option("--name", default=None, help="Install only the named job.")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print the unit files that would be written; touch nothing.",
    )
    @click.option("-y", "--yes", is_flag=True, default=False, help="Confirm the write.")
    @click.option(
        "--adopt",
        is_flag=True,
        default=False,
        help=(
            "Keep an existing supervisor of ANY mechanism instead of "
            "writing a competing one. Reports what it adopted, on stderr."
        ),
    )
    @click.option(
        "--force",
        is_flag=True,
        default=False,
        help="Overwrite even when another supervisor exists (reports loudly).",
    )
    def _install(name, dry_run, yes, adopt, force):
        U.do_install(
            _KIND,
            name=name,
            dry_run=dry_run,
            yes=yes,
            adopt=adopt,
            force=force,
        )


def _add_uninstall(group) -> None:
    @group.command(
        "uninstall",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Remove the `<name>.service` unit file(s).",
            examples=(
                Example(
                    "{prog} ecosystem dev service uninstall --dry-run",
                    "Preview only.",
                ),
                Example(
                    "{prog} ecosystem dev service uninstall --yes",
                    "Remove the unit files.",
                ),
            ),
        ),
    )
    @click.option("--name", default=None, help="Remove only the named job's unit.")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print which unit files would be removed; touch nothing.",
    )
    @click.option(
        "-y", "--yes", is_flag=True, default=False, help="Confirm the removal."
    )
    def _uninstall(name, dry_run, yes):
        U.do_uninstall(_KIND, name=name, dry_run=dry_run, yes=yes)


__all__ = ["register"]


# EOF
