#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``ecosystem dev timer <verb>`` — the ``kind="timer"`` CLI group.

A timer is periodic work; a service is a daemon. They are separate kinds
in ``jobs._kinds.ALLOWED_KINDS`` because the applicable fields differ —
a timer carries ``on_unit_active_sec`` and MUST have ``restart_policy="no"``
and ``watchdog_sec=None``; a service is the mirror image. Fusing them under
one ``systemd`` group put two kinds behind one surface while the validator
kept them apart.

Verbs, and why these
--------------------
``list`` ``status`` ``enable`` ``disable`` ``install`` ``uninstall``.

Deliberately ABSENT, rather than present and erroring:

* ``start`` / ``stop`` / ``restart`` — for a timer these are ambiguous in
  the worst way. ``systemctl start foo.timer`` starts the TIMER, not the
  job; an operator reaching for "start" almost always means "run the body
  now", which is ``ecosystem dev cron exec <name>`` (timer-kind jobs route
  their body through that same verb, see ``_jobs_cron``). Offering a verb
  that does the other thing is worse than not offering it.
* ``exec`` — it already exists on the ``cron`` group and covers BOTH
  cron-kind and timer-kind jobs. A second spelling would be a second thing
  to keep in agreement.

``enable``/``disable`` are the timer's real lifecycle: the unit file
persists, and enablement is what decides whether it fires.
"""

from __future__ import annotations

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup
from . import _jobs_units as U

_KIND = "timer"


def register(parent) -> None:
    """Mount the ``timer`` kind group on ``parent`` (``ecosystem dev``)."""

    @parent.group(
        _KIND,
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Federated kind='timer' periodic jobs across the ecosystem.",
            description=(
                'Periodic work declared as `kind="timer"` JobSpecs by any '
                "package registered under the `scitex_dev.jobs` entry-point "
                "group. Backed by a systemd `--user` Timer plus the oneshot "
                "Service it fires. "
                "NOT AVAILABLE ON EVERY HOST: macOS uses launchd and the "
                "Synology/QNAP NAS boxes ship no systemd, so verbs needing a "
                "user manager REFUSE with exit 3 and a named reason there. "
                '`kind="cron"` is the only mechanism available fleet-wide.',
            ),
            examples=(
                Example(
                    "{prog} ecosystem dev timer list",
                    "Every declared kind=timer job.",
                ),
                Example(
                    "{prog} ecosystem dev timer status sac.accounts-refresh",
                    "Installed? enabled? supervised by what?",
                ),
            ),
        ),
    )
    @click.pass_context
    def timer(ctx):
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    _add_list(timer)
    _add_status(timer)
    _add_enablement(timer)
    _add_install(timer)
    _add_uninstall(timer)


def _add_list(group) -> None:
    @group.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List every discovered kind='timer' job.",
            examples=(
                Example("{prog} ecosystem dev timer list", "Human-readable."),
                Example(
                    "{prog} ecosystem dev timer list --json",
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
            summary="Report install + supervision state for one timer.",
            examples=(
                Example(
                    "{prog} ecosystem dev timer status sac.accounts-refresh",
                    "Human-readable status.",
                ),
                Example(
                    "{prog} ecosystem dev timer status sac.accounts-refresh --json",
                    "Structured status.",
                ),
            ),
        ),
    )
    @click.argument("name")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def _status(name, as_json):
        U.do_status(_KIND, name=name, as_json=as_json)


def _add_enablement(group) -> None:
    """enable / disable — a timer's real lifecycle."""

    @group.command(
        "enable",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Enable and start the `<name>.timer` unit.",
            description=(
                "`systemctl --user enable --now <name>.timer`. MUTATING: "
                "needs --yes/-y; --dry-run prints the command and works on "
                "ANY host. Refuses with exit 3 and a named reason where no "
                "user manager exists.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem dev timer enable sac.accounts-refresh --dry-run",
                    "Show the systemctl command; change nothing.",
                ),
                Example(
                    "{prog} ecosystem dev timer enable sac.accounts-refresh --yes",
                    "Start firing on the declared cadence.",
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
    def _enable(name, dry_run, yes):
        U.do_systemctl(
            _KIND, "enable", name, dry_run=dry_run, yes=yes, extra=("--now",)
        )

    @group.command(
        "disable",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Disable and stop the `<name>.timer` unit.",
            description=(
                "`systemctl --user disable --now <name>.timer`. The unit "
                "FILE stays on disk — this stops the timer firing, it does "
                "not uninstall it. Use `uninstall` for that. "
                "MUTATING: needs --yes/-y. That guard is load-bearing here "
                "— disabling `sac.accounts-refresh` stops the fleet's SOLE "
                "OAuth refresher, and every account expires within one "
                "access-token lifetime.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem dev timer disable sac.accounts-refresh --dry-run",
                    "Show the systemctl command; change nothing.",
                ),
                Example(
                    "{prog} ecosystem dev timer disable sac.accounts-refresh --yes",
                    "Stop firing; keep the unit installed.",
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
    def _disable(name, dry_run, yes):
        U.do_systemctl(
            _KIND, "disable", name, dry_run=dry_run, yes=yes, extra=("--now",)
        )


def _add_install(group) -> None:
    @group.command(
        "install",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Write `<name>.service` + `<name>.timer` for timer jobs.",
            description=(
                "REFUSES when the job is ALREADY SUPERVISED by any "
                "mechanism — unit file, crontab line, or respawn loop. "
                "`sac.accounts-refresh` is the fleet's SOLE OAuth refresher "
                "and its refresh token is SINGLE-USE: two racing refreshers "
                "revoke each other and expire every account within hours, "
                "so a reinstall path that silently overwrote would be a "
                "fleet outage. Use --adopt to keep what exists, --force to "
                "overwrite deliberately.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem dev timer install --dry-run",
                    "Preview the unit text; works on any host.",
                ),
                Example(
                    "{prog} ecosystem dev timer install --name sac.accounts-refresh --adopt",
                    "Keep the existing refresher; write nothing.",
                ),
                Example(
                    "{prog} ecosystem dev timer install --yes",
                    "Write units for every declared timer.",
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
            summary="Remove `<name>.service` + `<name>.timer` unit files.",
            description=(
                "Both files: a timer owns the `.timer` that fires AND the "
                "oneshot `.service` it triggers, so removing one would "
                "leave the next install inheriting a stale body.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem dev timer uninstall --dry-run",
                    "Preview only.",
                ),
                Example(
                    "{prog} ecosystem dev timer uninstall --yes",
                    "Remove the unit files.",
                ),
            ),
        ),
    )
    @click.option("--name", default=None, help="Remove only the named job's units.")
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
