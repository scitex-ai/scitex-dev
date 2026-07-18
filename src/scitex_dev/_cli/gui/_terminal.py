#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`gui watch` + `gui start-tui` — the two live terminal surfaces.

`watch` is the former `ecosystem dashboard start` (rich live-refresh
table); `start-tui` is the former `ecosystem dashboard start-tui`
(textual keystroke-filter TUI), name unchanged. `start` was not carried
over as a verb because the doctrine reserves `start`/`stop` for
daemonized lifecycle, which `gui serve` / `gui stop` now own; the old
spelling still resolves through the Phase W alias in `_aliases.py`.
"""

from __future__ import annotations

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ._shared import resolve_packages

__all__ = ["register"]


def register(gui: click.Group) -> None:
    @gui.command(
        "watch",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Live-refresh the ecosystem state table in the terminal.",
            description=(
                "Re-gathers state every --interval seconds until Ctrl-C. "
                "Was `ecosystem dashboard start`; renamed because the "
                "doctrine reserves `start`/`stop` for daemonized lifecycle "
                "(`gui serve` / `gui stop`). For the browser view use "
                "`gui open`; for the keystroke-filter TUI, `gui start-tui`."
            ),
            examples=(
                Example("{prog} gui watch -vv", "More columns."),
                Example("{prog} gui watch --interval 10", "Slower refresh."),
                Example("{prog} gui watch --dry-run", "Print the refresh plan."),
            ),
        ),
    )
    @click.option("-v", "verbosity", count=True, default=1, help="Add -v / -vv / -vvv.")
    @click.option(
        "--gui",
        "as_gui",
        is_flag=True,
        help="Open the browser view instead (hands off to `gui open`).",
    )
    @click.option(
        "--interval",
        type=float,
        default=5.0,
        show_default=True,
        help="Refresh interval (seconds).",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the refresh plan (verbosity, interval) and exit.",
    )
    @click.option(
        "-y",
        "--yes",
        "yes",
        is_flag=True,
        help="No-op confirmation flag retained for §2 audit-cli compliance.",
    )
    @click.pass_context
    def gui_watch(ctx, verbosity, as_gui, interval, dry_run, yes):
        if dry_run:
            click.echo(
                f"would render: verbosity={verbosity} interval={interval}s "
                f"gui={'yes' if as_gui else 'no'}"
            )
            return
        del yes  # accepted for compliance; nothing to confirm
        if as_gui:
            # `dashboard start --gui` used to hard-error ("not yet wired
            # into the v0 dashboard"). The browser surface exists now, so
            # honour the flag by handing off to the canonical verb.
            ctx.invoke(gui.commands["open"])
            return

        from rich.console import Console
        from rich.live import Live

        from ..ecosystem._dashboard import gather_ecosystem_state
        from ..ecosystem._dashboard._render import render_table

        console = Console()
        try:
            with Live(
                render_table(
                    gather_ecosystem_state(verbosity=verbosity), verbosity=verbosity
                ),
                console=console,
                refresh_per_second=4,
                screen=False,
            ) as live:
                import time

                while True:
                    time.sleep(interval)
                    live.update(
                        render_table(
                            gather_ecosystem_state(verbosity=verbosity),
                            verbosity=verbosity,
                        )
                    )
        except KeyboardInterrupt:
            click.echo("\nstopped.", err=True)

    @gui.command(
        "start-tui",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Launch the htop-style TUI with a live keystroke filter.",
            description=(
                "Requires the optional `textual` package "
                "(pip install textual).\n\n"
                "Keys: `/` start filter, Escape clear filter, `r` refresh, "
                "`q` quit, j/k or arrows navigate rows, g/G jump to "
                "top/bottom."
            ),
            examples=(
                Example("{prog} gui start-tui", "Launch the TUI."),
                Example(
                    "{prog} gui start-tui -p scitex-io,scitex-stats",
                    "Limit to two packages.",
                ),
                Example("{prog} gui start-tui --dry-run", "Print the plan only."),
            ),
        ),
    )
    @click.option(
        "-v",
        "verbosity",
        count=True,
        default=1,
        help="Add -v / -vv / -vvv for more columns.",
    )
    @click.option(
        "--package",
        "-p",
        multiple=True,
        help="Limit to specific packages (comma-separated or repeat the flag).",
    )
    @click.option(
        "--jobs",
        "-j",
        default=16,
        show_default=True,
        type=int,
        help="Concurrent worker threads for enrichment.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print plan (verbosity, package count) and exit without launching.",
    )
    @click.option(
        "-y",
        "--yes",
        "yes",
        is_flag=True,
        help="No-op confirmation flag retained for §2 audit-cli compliance.",
    )
    def gui_start_tui(verbosity, package, jobs, dry_run, yes):
        packages_arg = resolve_packages(package)

        del yes  # accepted for §2 compliance
        if dry_run:
            n = len(packages_arg) if packages_arg else "all"
            click.echo(
                f"would launch TUI: verbosity={verbosity} packages={n} jobs={jobs}"
            )
            return

        try:
            from ..ecosystem._dashboard._tui import run_tui
        except ImportError as exc:
            click.echo(f"error: {exc}", err=True)
            raise SystemExit(2)

        try:
            run_tui(verbosity=verbosity, packages=packages_arg, workers=jobs)
        except ImportError as exc:
            click.echo(f"error: {exc}", err=True)
            raise SystemExit(2)


# EOF
