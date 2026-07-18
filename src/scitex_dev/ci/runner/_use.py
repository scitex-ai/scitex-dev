"""``scitex-dev ci runner use <target>`` — flip CI_RUNS_ON."""

from __future__ import annotations

import subprocess

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from . import config


def register(group: click.Group) -> None:
    @group.command(
        "use",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Flip CI_RUNS_ON between hosted and self-hosted.",
            description=(
                "Sends a PATCH to the repo Actions Variable CI_RUNS_ON.\n"
                "\n"
                "NOTE: requires a CLASSIC PAT with actions:variables:write. "
                "Set the SCITEX_DEV_GH_PAT environment variable."
            ),
            examples=(
                Example("{prog} ci runner use github", "Route CI to ubuntu-latest."),
                Example(
                    "{prog} ci runner use self-hosted",
                    "Route CI back to the scitex-ci runner.",
                ),
            ),
        ),
    )
    @click.argument("target", type=click.Choice(["github", "self-hosted"], case_sensitive=False))
    def use_cmd(target: str) -> None:
        cfg = config.load_runner_config()
        var_name = cfg["github"]["variable_name"]
        repo = cfg["github"]["default_repo"]

        if target == "github":
            value = '"ubuntu-latest"'
            label = "hosted"
        else:
            value = '["self-hosted","scitex-ci"]'
            label = "self-hosted"

        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/actions/variables/{var_name}",
                "-X",
                "PATCH",
                "-f",
                f"value={value}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise click.ClickException(
                f"Failed to flip CI_RUNS_ON to {label}: {result.stderr.strip()}"
            )

        click.echo(f"CI_RUNS_ON → {value} ({label})")
        click.secho(
            "NOTE: requires a CLASSIC PAT with actions:variables:write. "
            "Set SCITEX_DEV_GH_PAT environment variable.",
            fg="yellow",
        )
