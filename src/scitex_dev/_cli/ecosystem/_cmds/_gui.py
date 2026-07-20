#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `gui` group -- fan-out launcher for the leaf-package GUIs.

Distinct from the top-level `scitex-dev gui` group (scitex-dev's OWN
dashboard): this `ecosystem gui` group opens the OTHER leaf packages'
browser GUIs (todo board, live-paper, storage, figrecipe, scholar,
writer) at once. Ports come from the scitex-dev-owned SSOT
``scitex_dev._ecosystem.gui_registry``.
"""

from __future__ import annotations

import json
import webbrowser

import click

from ...._ecosystem.gui_registry import gui_surfaces
from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def register(ecosystem):
    @ecosystem.group(
        "gui",
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Open the leaf-package browser GUIs (fan-out launcher).",
            description=(
                "Fan-out launcher for the OTHER SciTeX leaf packages' "
                "browser GUIs (todo board, live-paper, storage, figrecipe, "
                "scholar, writer). Ports come from the scitex-dev-owned "
                "3129X port-registry SSOT. This is NOT scitex-dev's own "
                "dashboard -- that is the top-level `gui` group."
            ),
            examples=(
                Example("{prog} ecosystem gui list", "Table of every leaf GUI + URL."),
                Example("{prog} ecosystem gui open", "Open every leaf GUI in a browser tab."),
            ),
        ),
    )
    def gui():
        pass

    @gui.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List the leaf-package GUIs (package, ports, URL).",
            examples=(
                Example("{prog} ecosystem gui list", "Table of package, ports, URL."),
                Example("{prog} ecosystem gui list --json", "Structured JSON output."),
            ),
        ),
    )
    @click.option("--host", default="localhost", show_default=True, help="URL host.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def gui_list(host, as_json):
        surfaces = gui_surfaces()
        if as_json:
            items = [
                {
                    "package": s.package,
                    "actual_port": s.actual_port,
                    "target_port": s.target_port,
                    "path": s.path,
                    "url": s.url(host=host),
                }
                for s in surfaces
            ]
            click.echo(json.dumps({"surfaces": items}))
            return

        header = f"  {'PACKAGE':22s} {'ACTUAL':>7s} {'TARGET':>7s}  URL"
        click.echo(header)
        for s in surfaces:
            click.echo(
                f"  {s.package:22s} {s.actual_port:>7d} {s.target_port:>7d}  "
                f"{s.url(host=host)}"
            )

    @gui.command(
        "open",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Open browser tab(s) for the named leaf GUIs (or all).",
            description=(
                "Opens a browser tab for each named package (or every leaf "
                "GUI when none are named), using the ACTUAL live port. "
                "Best-effort via webbrowser.open; each URL is printed. Use "
                "--dry-run to print the URLs without opening a browser."
            ),
            examples=(
                Example("{prog} ecosystem gui open", "Open every leaf GUI."),
                Example("{prog} ecosystem gui open scitex-writer", "Open one package."),
                Example("{prog} ecosystem gui open --dry-run", "Print URLs, open nothing."),
            ),
        ),
    )
    @click.argument("packages", nargs=-1)
    @click.option("--host", default="localhost", show_default=True, help="URL host.")
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the URLs without opening a browser.",
    )
    def gui_open(packages, host, dry_run):
        surfaces = gui_surfaces()
        by_name = {s.package: s for s in surfaces}

        if packages:
            unknown = [p for p in packages if p not in by_name]
            if unknown:
                known = ", ".join(sorted(by_name))
                raise click.UsageError(
                    f"unknown package(s): {', '.join(unknown)} — known: {known}"
                )
            selected = [by_name[p] for p in packages]
        else:
            selected = surfaces

        for s in selected:
            target = s.url(host=host)
            if dry_run:
                click.echo(target)
            else:
                click.echo(f"opening {s.package}: {target}")
                webbrowser.open(target)
