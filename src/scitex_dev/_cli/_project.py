#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev project`` — CUI surface for the active-project primitive.

Thin ``register(main)`` entry-point (mirrors ``_cli/_trace_env.py``); all
real logic lives in the ``scitex_dev.project`` engine package.

- ``project use <owner/name|all>`` — persist the selection
- ``project clear`` — drop the persisted selection
- ``project current [--json]`` — show the resolved selection and its source
"""

from __future__ import annotations

import json

import click

from ..project import (
    ACTIVE_PROJECT_ENV,
    clear_active_project,
    resolve_project,
    set_active_project,
)


def register(main: click.Group) -> None:
    """Attach the ``project`` group to the top-level click group."""

    @main.group("project")
    def project_grp() -> None:
        """Select the active SciTeX project (CUI-level primitive)."""

    @project_grp.command("use")
    @click.argument("ref")
    def project_use(ref: str) -> None:
        """Persist REF ('owner/name' or 'all') as the active project."""
        try:
            click.echo(set_active_project(ref))
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    @project_grp.command("clear")
    def project_clear() -> None:
        """Drop the persisted active-project selection."""
        if clear_active_project():
            click.echo("cleared")
        else:
            click.echo("nothing selected")

    @project_grp.command("current")
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
    def project_current(as_json: bool) -> None:
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
