#!/usr/bin/env python3
"""``scitex-dev project`` — CUI surface for the active-project primitive.

Thin ``register(main)`` entry-point (mirrors ``_cli/_trace_env.py``); all
real logic lives in the ``scitex_dev.project`` engine package.

- ``project use <owner/name|all>`` — persist the selection
- ``project clear`` — drop the persisted selection
- ``project get [--json]`` — return the resolved selection and its source
- ``project current`` — deprecated compatibility spelling for ``project get``
"""

from __future__ import annotations

import json

import click

from .._ecosystem.click_compat import deprecated_alias
from .._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup
from ..project import (
    ACTIVE_PROJECT_ENV,
    clear_active_project,
    resolve_project,
    set_active_project,
)


def register(main: click.Group) -> None:
    """Attach the ``project`` group to the top-level click group."""

    @main.group(
        "project",
        cls=SpecGroup,
        command_categories=[("Core", ["use", "clear"]), ("Introspection", ["get"])],
        help_spec=CliHelp(
            summary="Select the active SciTeX project.",
            examples=(
                Example("{prog} project use synthetic/owned", "Select a project."),
            ),
            config_resolution=(
                "Explicit reference, then SCITEX_PROJECT, then the persisted selection.",
                "State lives under SCITEX_DIR/scitex-dev (default: ~/.scitex/scitex-dev).",
            ),
        ),
    )
    def project_grp() -> None:
        """Select the active SciTeX project (CUI-level primitive)."""

    @project_grp.command(
        "use",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Persist REF ('owner/name' or 'all') as the active project.",
            examples=(
                Example("{prog} project use synthetic/owned", "Select a project."),
                Example("{prog} project use all", "Select all projects."),
            ),
            exit_codes=((0, "Selection persisted."), (1, "Invalid project reference.")),
        ),
    )
    @click.argument("ref")
    def project_use(ref: str) -> None:
        """Persist REF ('owner/name' or 'all') as the active project."""
        try:
            click.echo(set_active_project(ref))
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    @project_grp.command(
        "clear",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Drop the persisted active-project selection.",
            examples=(
                Example("{prog} project clear", "Clear the persisted selection."),
            ),
            exit_codes=((0, "Selection cleared or already absent."),),
        ),
    )
    def project_clear() -> None:
        """Drop the persisted active-project selection."""
        if clear_active_project():
            click.echo("cleared")
        else:
            click.echo("nothing selected")

    @project_grp.command(
        "get",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Show the resolved active project and where it came from.",
            examples=(
                Example("{prog} project get", "Return the active project."),
                Example("{prog} project get --json", "Emit machine-readable state."),
            ),
            exit_codes=(
                (0, "Current selection reported, including an absent selection."),
            ),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
    def project_get(as_json: bool) -> None:
        """Show the resolved active project and where it came from."""
        import os

        ref = resolve_project()
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "project": ref,
                        "env": os.environ.get(ACTIVE_PROJECT_ENV, "") or None,
                    }
                )
            )
        else:
            click.echo(ref if ref is not None else "(none)")

    # Phase W in 0.62; move to Phase E in 0.63 and remove in 0.64.
    # The shared helper forwards options and warns once per shell on stderr.
    deprecated_alias(
        project_grp,
        "current",
        target=project_get,
        target_name="project get",
        remove_in="0.64",
    )
