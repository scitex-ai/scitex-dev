#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""§13 — the canonical `dev` group for scitex-dev's own self-maintenance.

Operator directive (doctrine ``general/03_interface/02_cli/20_dev-commands.md``):
every self-maintenance surface a package ships — daemon, cron, systemd,
hooks, skills, shell — mounts under ONE group name, ``dev``.

    A package's top-level CLI is its DOMAIN. Self-maintenance plumbing is
    housekeeping, and housekeeping belongs under `dev`.
    `<pkg> --help` then reads as the tool, not the tool's own upkeep.

THE DISCRIMINATOR, applied here: "is this command about the tool's DOMAIN,
or about maintaining/developing the tool itself?"

  moved to `dev`   cron, hooks, skills
  kept top level   ecosystem, linter, gate, mcp, creds, service, host,
                   doctor, docs, gui, ci-runner, rename-symbols, …

scitex-dev carries this as a LEAF like any other package: ``scitex-dev dev
…`` is scitex-dev's OWN scope. The fleet-wide federation over every
package's ``dev`` is a different surface — ``scitex-dev ecosystem dev …``.

WHY scitex-dev IS FIRST, and it is not politeness: the §13 audit
(``_cli/audit/_summary/_dev_group.py``) has been firing against scitex-dev
itself on every run since it shipped. A convention whose owner is its worst
violator cannot be enforced on anyone else — measured 2026-08-02, that
exact gap led two peer agents to conclude independently, from an adoption
count of zero, that the convention did not exist.
"""

from __future__ import annotations

import click

from .._ecosystem.click_compat import deprecated_alias

#: Version the Phase W aliases disappear in. Deliberately distant: the old
#: spellings live in scripts, cron lines, agent prompts and documentation
#: across the fleet, and none of those are greppable from here.
_ALIAS_REMOVE_IN = "0.50"

#: Commands moving from top level into `dev`, with the registrar that
#: mounts each. Data rather than code so the alias loop below cannot
#: drift from the mount loop — the failure that would leave a command
#: mounted with no alias, resolving nowhere.
_MOVED = ("cron", "hooks", "skills")


def register_dev_group(main: click.Group) -> click.Group:
    """Mount ``dev`` on *main* and populate it with self-maintenance surfaces.

    The group itself is built by ``_cli.dev.register_dev_commands`` — the
    module that already carries the §13 help spec and the ``secret`` verb.
    This function calls THAT builder rather than declaring its own
    ``@main.group("dev")``: two builders would each register a ``dev`` on
    ``main``, the later call would silently replace the earlier group, and
    whichever surfaces the loser had mounted would vanish with it. Measured
    here on 2026-08-03 — a second group defined at this call site left
    ``dev`` holding ``secret`` alone, with cron/hooks/skills gone and no
    error anywhere, because click's ``add_command`` is a dict assignment.

    Returns the group so the caller can pass it to registrars that live
    elsewhere (``register_integration_commands`` takes both).
    """
    from .dev import register_dev_commands
    from .skills._manage import register_skills_commands

    dev = register_dev_commands(main)
    register_skills_commands(dev)
    return dev


def install_dev_aliases(main: click.Group, dev: click.Group) -> None:
    """Phase W warn-forward aliases for every command that moved.

    Called AFTER all registrars have populated ``dev``, because an alias
    must point at a command that exists — building it earlier would
    silently produce an alias to nothing, which is the exact failure this
    migration is supposed to be invisible against.

    Not a courtesy. A CLI whose old spelling stops resolving breaks every
    script, cron line and agent prompt that used it, and none of those are
    greppable from this repository.
    """
    for name in _MOVED:
        command = dev.commands.get(name)
        if command is None:
            # Fail loud rather than skip: a missing command here means a
            # registrar did not run, and a silently-absent alias is
            # indistinguishable from a successful migration.
            raise RuntimeError(
                f"§13 dev-group migration: {name!r} is not mounted on `dev`, "
                "so its Phase W alias cannot be built. A registrar did not "
                "run — fix the mount rather than dropping the alias, or the "
                f"old `scitex-dev {name}` spelling resolves nowhere."
            )
        deprecated_alias(
            main,
            name,
            target=command,
            target_name=f"dev {name}",
            remove_in=_ALIAS_REMOVE_IN,
            phase="warn",
        )


#: Federated job surfaces moving from `ecosystem <verb>` to
#: `ecosystem dev <verb>`. Both aggregate `scitex_dev.jobs` entry points
#: across every installed package, which is what makes them the FEDERATED
#: half of §13 rather than scitex-dev's own upkeep.
_ECOSYSTEM_MOVED = ("cron", "systemd")


def register_ecosystem_dev_group(ecosystem: click.Group) -> click.Group:
    """Mount ``ecosystem dev`` — the federation over every package's ``dev``.

    Two distinct surfaces share the name, and conflating them is the easy
    mistake:

    * ``scitex-dev dev …``           scitex-dev's OWN upkeep, as a leaf.
    * ``scitex-dev ecosystem dev …`` the aggregate across every installed
                                     package's ``dev`` (scitex-dev's
                                     included).

    ``ecosystem up`` / ``run`` / ``status`` deliberately stay at
    ``ecosystem`` level: they bring the ecosystem itself up, which is this
    command's domain, not per-package housekeeping.
    """
    from .._ecosystem.help_spec import CliHelp, Example, SpecGroup
    from .ecosystem._cmds import _jobs_cron, _jobs_systemd

    @ecosystem.group(
        "dev",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary=(
                "Federated self-maintenance across every installed package."
            ),
            description=(
                "Aggregates the `scitex_dev.jobs` entry points each package "
                "publishes, so one command reaches the whole ecosystem's "
                "scheduled-job surfaces rather than one package's. Distinct "
                "from `scitex-dev dev`, which is scitex-dev's OWN upkeep as "
                "a leaf."
            ),
            examples=(
                Example(
                    "{prog} ecosystem dev cron list",
                    "List every package's cron jobs.",
                ),
                Example(
                    "{prog} ecosystem dev systemd install",
                    "Install every package's units.",
                ),
            ),
        ),
    )
    @click.pass_context
    def dev(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    _jobs_cron.register(dev)
    _jobs_systemd.register(dev)

    for name in _ECOSYSTEM_MOVED:
        command = dev.commands.get(name)
        if command is None:
            raise RuntimeError(
                f"§13 ecosystem-dev migration: {name!r} is not mounted on "
                "`ecosystem dev`, so its Phase W alias cannot be built. Fix "
                "the mount rather than dropping the alias — the old "
                f"`scitex-dev ecosystem {name}` spelling is in crontabs and "
                "unit files that are not greppable from here."
            )
        deprecated_alias(
            ecosystem,
            name,
            target=command,
            target_name=f"ecosystem dev {name}",
            remove_in=_ALIAS_REMOVE_IN,
            phase="warn",
        )
    return dev


__all__ = [
    "register_dev_group",
    "install_dev_aliases",
    "register_ecosystem_dev_group",
]


# EOF
