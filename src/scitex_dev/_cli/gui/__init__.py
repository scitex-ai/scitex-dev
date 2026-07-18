#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev gui` — the canonical §12 GUI command group.

One group per package for every browser-based surface, with four fixed
verbs (`open`, `serve`, `status`, `stop`) plus the terminal surfaces the
same state layer feeds. Doctrine:
``_skills/general/03_interface/02_cli/19_gui-commands.md``; the audit
rule that enforces it is
``_cli/audit/_summary/_gui_group.py``.

Layout::

    gui open [SURFACE]   browser view, auto-serving first   (canonical)
    gui serve            foreground headless server         (canonical)
    gui status           running? where? tri-state          (canonical)
    gui stop             stop the running instance          (canonical)
    gui list             one-shot state table               (was `dashboard list`)
    gui watch            live-refresh table                 (was `dashboard start`)
    gui start-tui        textual TUI                        (was `dashboard start-tui`)
    gui export           json/csv/md/org/pdf dump           (was `dashboard export`)

Process lifecycle rides on the shared `scitex_dev.gui_runtime.GuiRuntime`
primitive rather than a private state-file implementation — that is the
whole reason the primitive was extracted.
"""

from __future__ import annotations

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecGroup

__all__ = ["register"]


GUI_HELP_SPEC = CliHelp(
    summary="Ecosystem dashboard: browser view, live tables, and exports.",
    description=(
        "The canonical GUI group (doctrine 19_gui-commands.md). `open` is "
        "the user-facing entry point — it auto-serves the dashboard and "
        "opens it in a browser; `serve` runs the same server in the "
        "foreground, headless; `status` and `stop` manage that instance.\n\n"
        "`list`, `watch`, `start-tui` and `export` render the SAME state "
        "layer in the terminal, so the browser view and the table view "
        "can never drift apart.\n\n"
        "Migrated from `ecosystem dashboard` / `ecosystem start-dashboard`; "
        "both old paths still work and print one deprecation line."
    ),
    examples=(
        Example("{prog} gui open", "Serve if needed, then open a browser."),
        Example("{prog} gui status --json", "Is it running, and where?"),
        Example("{prog} gui list -vv", "One-shot state table in the terminal."),
    ),
)


def register(main: click.Group) -> click.Group:
    """Register the `gui` group on the root CLI; return the group."""

    @main.group(
        "gui",
        cls=SpecGroup,
        help_spec=GUI_HELP_SPEC,
        invoke_without_command=True,
    )
    @click.pass_context
    def gui(ctx):
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    from . import _aliases, _export, _lifecycle, _list, _terminal

    _lifecycle.register(gui)
    _list.register(gui)
    _terminal.register(gui)
    _export.register(gui)
    _aliases.register_in_group(gui)

    # Phase W back-compat for the two legacy `ecosystem` entry points.
    # Resolved off `main` so the caller does not have to thread the
    # ecosystem group through; a CLI built without it simply skips them.
    ecosystem = main.commands.get("ecosystem")
    if isinstance(ecosystem, click.Group):
        _aliases.register_on_ecosystem(ecosystem, gui)

    return gui


# EOF
