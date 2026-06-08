"""``scitex-dev ci runner use github|self-hosted`` — flip CI_RUNS_ON."""

from __future__ import annotations

import subprocess

import click

from . import config


def register(group: click.Group) -> None:
    @group.group("use", invoke_without_command=True)
    @click.pass_context
    def use(ctx: click.Context) -> None:
        """Flip CI_RUNS_ON between hosted and self-hosted."""
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @use.command("github")
    def use_github() -> None:
        """Flip CI_RUNS_ON to hosted ubuntu-latest.

        \b
        Sends a PATCH to the repo Actions Variable CI_RUNS_ON:
          value = '"ubuntu-latest"'
        """
        cfg = config.load_runner_config()
        var_name = cfg["github"]["variable_name"]
        repo = cfg["github"]["default_repo"]

        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/actions/variables/{var_name}",
                "-X",
                "PATCH",
                "-f",
                'value="ubuntu-latest"',
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise click.ClickException(
                f"Failed to flip CI_RUNS_ON to github-hosted: {result.stderr.strip()}"
            )

        click.echo(f"CI_RUNS_ON → 'ubuntu-latest' (hosted)")
        click.secho(
            "NOTE: requires a CLASSIC PAT with actions:variables:write. "
            "Set SCITEX_DEV_GH_PAT environment variable.",
            fg="yellow",
        )

    @use.command("self-hosted")
    def use_self_hosted() -> None:
        """Flip CI_RUNS_ON back to self-hosted.

        \b
        Sends a PATCH to the repo Actions Variable CI_RUNS_ON:
          value = '["self-hosted","scitex-ci"]'
        """
        cfg = config.load_runner_config()
        var_name = cfg["github"]["variable_name"]
        repo = cfg["github"]["default_repo"]

        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/actions/variables/{var_name}",
                "-X",
                "PATCH",
                "-f",
                'value=["self-hosted","scitex-ci"]',
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise click.ClickException(
                f"Failed to flip CI_RUNS_ON to self-hosted: {result.stderr.strip()}"
            )

        click.echo('CI_RUNS_ON → ["self-hosted","scitex-ci"] (self-hosted)')


# EOF
