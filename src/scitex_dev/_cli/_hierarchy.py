"""Metadata-only hierarchy declaration diagnostics."""

import json
from dataclasses import asdict
from pathlib import Path

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def register_hierarchy_commands(main):
    """Attach the installed hierarchy-provider catalog to the CLI."""

    @main.group(
        "hierarchy",
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Inspect installed package hierarchy declarations without loading them.",
            examples=(
                Example("{prog} hierarchy list --json", "Read hierarchy declarations."),
            ),
        ),
    )
    def hierarchy():
        pass

    @hierarchy.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List provider metadata; this does not build or enable a hierarchy.",
            examples=(
                Example(
                    "{prog} hierarchy list --package scitex-sdk --json",
                    "Inspect one installed owner without importing its provider.",
                ),
            ),
        ),
    )
    @click.option("--package", help="Filter by normalized owning distribution.")
    @click.option(
        "--path",
        "paths",
        multiple=True,
        type=click.Path(exists=True, file_okay=False, path_type=Path),
        help="Restrict discovery to these installed metadata directories (repeatable).",
    )
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit declaration rows as JSON."
    )
    @click.pass_context
    def list_command(ctx, package, paths, as_json):
        from ..hierarchy_providers import list_hierarchy_providers

        try:
            rows = list_hierarchy_providers(package=package, path=paths or None)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        inherited = (ctx.find_root().obj or {}).get("json", False)
        if as_json or inherited:
            click.echo(json.dumps([asdict(row) for row in rows], indent=2))
        else:
            click.echo(f"{len(rows)} hierarchy provider declarations (metadata only).")
            for row in rows:
                click.echo(
                    f"{row.name}: {row.target} [{row.version or 'version unknown'}]"
                )

    return hierarchy
