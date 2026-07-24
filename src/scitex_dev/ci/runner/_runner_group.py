"""Register the ``scitex-dev ci runner`` click group."""

from __future__ import annotations

import click

from ..._ecosystem.help_spec import CliHelp, SpecGroup


def register(ci_group: click.Group) -> click.Group:
    """Register ``scitex-dev ci runner`` on the given ci group."""

    @ci_group.group(
        "runner",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Self-hosted GitHub Actions runner lifecycle.",
            description=(
                "\b\n"
                "Verbs:\n"
                "  status            — runner state + CI_RUNS_ON + xdist tuning\n"
                "  use <target>      — flip CI_RUNS_ON (target: github|self-hosted)\n"
                "  ensure            — SOLVER: keep lease + N runners alive "
                "(cron-safe)\n"
                "  up                — start the persistent runner\n"
                "  down              — deregister the runner + stop it\n"
                "  renew             — renew the SLURM CI lease job\n"
                "  register <repo>   — deploy the canonical org-reusable "
                "ci.yml caller (alias of ecosystem ci-template apply)\n"
                "  preflight         — fail-loud CI-readiness gate (for pre-push)\n"
                "  validate-health   — tri-state health signal (up/wedged/unknown)"
            ),
        ),
    )
    @click.pass_context
    def runner(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    from ._status import register as register_status
    from ._use import register as register_use
    from ._ensure_cmd import register as register_ensure
    from ._up import register as register_up
    from ._down import register as register_down
    from ._renew import register as register_renew
    from ._register import register as register_register
    from ._preflight import register as register_preflight
    from ._watchdog import register as register_watchdog

    register_status(runner)
    register_use(runner)
    register_ensure(runner)
    register_up(runner)
    register_down(runner)
    register_renew(runner)
    register_register(runner)
    register_preflight(runner)
    register_watchdog(runner)

    return runner


# EOF
