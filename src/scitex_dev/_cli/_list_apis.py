#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev list-python-apis`` — public API tree lister.

Extracted from ``_root.py`` to keep that orchestrator under the
per-file line budget. Registers a single ``list-python-apis`` command
on the main click group.
"""

from __future__ import annotations

import json

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register_list_python_apis_command(main: click.Group) -> None:
    """Register ``scitex-dev list-python-apis`` on ``main``."""

    @main.command(
        "list-python-apis",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List Python APIs (scitex-dev public API tree).",
            examples=(
                Example("{prog} list-python-apis", "Names only."),
                Example(
                    "{prog} list-python-apis -v --json",
                    "Names + first doc line, as JSON.",
                ),
            ),
        ),
    )
    @click.option(
        "-v",
        "--verbose",
        count=True,
        help="Verbosity: -v sig+doc1, -vv full doc.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def list_python_apis(verbose, as_json):
        import inspect

        import scitex_dev

        items = []
        for name in sorted(scitex_dev.__all__):
            obj = getattr(scitex_dev, name, None)
            if obj is None:
                continue
            if inspect.isclass(obj):
                kind = "C"
            elif callable(obj):
                kind = "F"
            else:
                kind = "V"
            doc = inspect.getdoc(obj) or ""
            items.append({"name": name, "type": kind, "doc": doc})

        if as_json:
            click.echo(json.dumps(items, indent=2))
            return

        click.secho(
            f"scitex-dev public API ({len(items)} items):",
            fg="cyan",
            bold=True,
        )
        for item in items:
            t = item["type"]
            click.echo(f"  [{t}] {item['name']}")
            if verbose >= 1 and item["doc"]:
                desc = item["doc"].split("\n")[0][:70]
                click.echo(f"      {desc}")


__all__ = ["register_list_python_apis_command"]


# EOF
