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

    from . import _export, _lifecycle, _list, _terminal

    _lifecycle.register(gui)
    _list.register(gui)
    _terminal.register(gui)
    _export.register(gui)

    # The Phase W back-compat aliases (`gui start`, `ecosystem dashboard`,
    # `ecosystem start-dashboard`) declared remove_in="0.34" and are gone as
    # of 0.50 — sixteen minor versions past their own deadline. A ladder
    # whose last rung is never climbed is not a migration, it is a permanent
    # second spelling, which is exactly what the ladder existed to avoid.
    return gui


# EOF
