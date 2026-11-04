"""Metadata-only CLI eligibility diagnostics."""

import json
from dataclasses import asdict

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def register_cli_provider_commands(main):
    """Attach one diagnostic view over the public installed metadata reader."""

    @main.group(
        "cli",
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Inspect installed CLI exposure declarations and decisions.",
            examples=(
                Example("{prog} cli list --json", "Read installed CLI metadata."),
            ),
        ),
    )
    def cli():
        pass

    @cli.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List CLI eligibility without importing or executing commands.",
            examples=(
                Example(
                    "{prog} cli list --package scitex-dev --json",
                    "Inspect one installed owner.",
                ),
            ),
        ),
    )
    @click.option("--package", help="Filter by normalized owning distribution.")
    @click.option("--json", "as_json", is_flag=True, help="Emit provider rows as JSON.")
    def list_commands(package, as_json):
        from ..cli_providers import list_cli_providers

        try:
            rows = list_cli_providers(package=package)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        if as_json:
            click.echo(json.dumps([asdict(row) for row in rows], indent=2))
        else:
            for row in rows:
                click.echo(
                    f"{row.name or '-'}: {row.distribution or '?'} [{row.status}] {row.reason}"
                )

    return cli
