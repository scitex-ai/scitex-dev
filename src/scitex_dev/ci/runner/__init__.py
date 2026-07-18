"""``scitex-dev ci runner …`` — self-hosted GitHub Actions runner management.

Verbs:
  * ``status``     — runner state + CI_RUNS_ON + xdist tuning info
  * ``status …``   — alias: ``scitex-dev ci runner status``
  * ``use github``       — flip CI_RUNS_ON to hosted ubuntu-latest
  * ``use self-hosted``  — flip CI_RUNS_ON back to self-hosted
  * ``ensure``           — SOLVER: keep the scitex-hpc reservation + N runners
                           alive across the 7-day SLURM walltime (cron-safe)
  * ``up``               — start the persistent runner on the HPC node
  * ``down``             — deregister the runner + stop it
  * ``renew``            — renew the SLURM CI lease job
  * ``onboard <repo>``   — copy the ci.yml template into a repo + set vars
  * ``validate-health``  — tri-state health signal (up/wedged/unknown); FAIL
                           LOUD, never silently falls back to a hosted runner
"""

from __future__ import annotations

import click

from ..._ecosystem.help_spec import CliHelp, SpecGroup


def register_ci_runner_commands(main_group: click.Group) -> click.Group:
    """Register ``scitex-dev ci`` group on the given main group."""

    @main_group.group(
        "ci",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="CI infrastructure — runner management and reusable workflows.",
            description=(
                "\b\n"
                "Verbs:\n"
                "  runner   — self-hosted GitHub Actions runner lifecycle"
            ),
        ),
    )
    @click.pass_context
    def ci(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    from . import _runner_group

    _runner_group.register(ci)
    return ci
