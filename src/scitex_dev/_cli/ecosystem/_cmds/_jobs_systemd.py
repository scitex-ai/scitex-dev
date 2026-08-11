#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``ecosystem dev systemd`` — DEPRECATED alias over ``service`` + ``timer``.

This group was organised by MECHANISM. It fused ``kind="service"`` and
``kind="timer"`` — two kinds the model keeps apart, with genuinely
different applicable fields — behind one surface, while
``jobs._kinds.ALLOWED_KINDS`` has been ``{"service", "timer", "cron"}``
since #153 and ``kind="systemd"`` raises ``ValueError``.

The cost of that mismatch is measured, not theoretical: ``sac dev systemd
list`` filtered ``kind="systemd"``, matched nothing, and reported "No sac
systemd-kind jobs." with exit 0 for weeks — hiding all four of sac's
timers, including the fleet's sole OAuth refresher. A CLI group whose
filter can only ever return zero jobs looks exactly like a healthy empty
fleet.

The replacements are ``ecosystem dev service`` and ``ecosystem dev timer``.

Why the alias still exists
--------------------------
The old spelling lives in crontabs, unit files, shell scripts, agent
prompts and documentation across the fleet, none of which are greppable
from this repository. Removing it outright would break them silently. So
it forwards, warns ON STDERR, and carries its own expiry in code.

Machine-readable expiry
-----------------------
:data:`DEPRECATION` is data, not prose in a docstring, because an auditor
rule FAILS once ``remove_after`` passes. A sunset that only a human can
read is a sunset nobody enforces.
"""

from __future__ import annotations

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup

#: The sunset, in code so a static auditor can enforce it.
#:
#: ``remove_after`` is the date this alias must be GONE by, not a hint.
#: The sibling auditor rule reads these three keys; keep them literal
#: strings in this exact shape.
DEPRECATION: dict[str, str] = {
    "deprecated": "2026-08",
    "remove_after": "2026-10",
    "replacement": "ecosystem dev service / ecosystem dev timer",
}

#: Kinds this alias fans out over, in the order results are concatenated.
_ALIASED_KINDS = ("service", "timer")

_WARNING = (
    "DEPRECATED: `ecosystem dev systemd` groups two DIFFERENT JobSpec kinds "
    "(service, timer) under one mechanism name. Use "
    f"`{DEPRECATION['replacement']}` instead. "
    f"Deprecated {DEPRECATION['deprecated']}; removed after "
    f"{DEPRECATION['remove_after']}."
)


def warn_deprecated() -> None:
    """Emit the deprecation notice — ALWAYS to stderr, never stdout.

    stdout is the payload. A sibling measured a stale-registry ``WARN:``
    reaching stdout and corrupting ``sac host list --json``, turning 7
    tests red across three unrelated PRs. A deprecation notice that
    corrupts the output of the command it is deprecating is worse than
    silence, so this never touches stdout — ``systemd list --json`` stays
    parseable with the deprecation path fully active.
    """
    click.echo(_WARNING, err=True)


def register(parent) -> None:
    """Mount the deprecated ``systemd`` alias group on ``parent``."""

    @parent.group(
        "systemd",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="(deprecated) Use `ecosystem dev service` / `... timer`.",
            description=(
                "Organised by MECHANISM, so it fuses kind='service' and "
                "kind='timer' — two kinds with different applicable fields "
                "that the JobSpec validator already keeps apart. Forwards "
                "to the kind groups and warns on stderr. "
                f"Deprecated {DEPRECATION['deprecated']}; removed after "
                f"{DEPRECATION['remove_after']}.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem dev systemd list",
                    "(deprecated) service + timer jobs, concatenated.",
                ),
                Example(
                    "{prog} ecosystem dev service list",
                    "The replacement for the service half.",
                ),
            ),
        ),
    )
    @click.pass_context
    def systemd(ctx):
        warn_deprecated()
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    systemd._deprecation = dict(DEPRECATION)

    _add_list(systemd)
    _add_install(systemd)
    _add_uninstall(systemd)


def _add_list(group) -> None:
    @group.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="(deprecated) List kind=service + kind=timer jobs.",
            examples=(
                Example(
                    "{prog} ecosystem dev systemd list --json",
                    "(deprecated) JSON on stdout; the warning is on stderr.",
                ),
            ),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def _list(as_json):
        from . import _jobs_units as U

        jobs = [j for k in _ALIASED_KINDS for j in U.jobs_for(k)]
        if as_json:
            import json

            click.echo(json.dumps([U.job_dict(j.kind, j) for j in jobs]))
            return
        if not jobs:
            click.echo("No service- or timer-kind jobs discovered.")
            return
        for job in jobs:
            click.echo(f"  {job.name:34s} kind={job.kind}")
            click.echo(f"  {'':34s} {job.description}")


def _add_install(group) -> None:
    @group.command(
        "install",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="(deprecated) Install units for service + timer jobs.",
            examples=(
                Example(
                    "{prog} ecosystem dev systemd install --dry-run",
                    "(deprecated) Preview both kinds' units.",
                ),
            ),
        ),
    )
    @click.option("--name", default=None, help="Install only the named job.")
    @click.option("--dry-run", is_flag=True, default=False, help="Preview only.")
    @click.option("-y", "--yes", is_flag=True, default=False, help="Confirm.")
    @click.option("--adopt", is_flag=True, default=False, help="Keep existing.")
    @click.option("--force", is_flag=True, default=False, help="Overwrite.")
    def _install(name, dry_run, yes, adopt, force):
        from . import _jobs_units as U

        for kind in _ALIASED_KINDS:
            if name is not None and not any(j.name == name for j in U.jobs_for(kind)):
                continue
            U.do_install(
                kind,
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
            summary="(deprecated) Remove units for service + timer jobs.",
            examples=(
                Example(
                    "{prog} ecosystem dev systemd uninstall --dry-run",
                    "(deprecated) Preview what would be removed.",
                ),
            ),
        ),
    )
    @click.option("--name", default=None, help="Remove only the named job.")
    @click.option("--dry-run", is_flag=True, default=False, help="Preview only.")
    @click.option("-y", "--yes", is_flag=True, default=False, help="Confirm.")
    def _uninstall(name, dry_run, yes):
        from . import _jobs_units as U

        for kind in _ALIASED_KINDS:
            if name is not None and not any(j.name == name for j in U.jobs_for(kind)):
                continue
            U.do_uninstall(kind, name=name, dry_run=dry_run, yes=yes)


__all__ = ["DEPRECATION", "register", "warn_deprecated"]


# EOF
