#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`ecosystem start-dashboard` — the dashboard web-UI entry point.

Back-compat shim: the `start-dashboard` name predates the `dashboard`
group and is preserved for external scripts/CI. Split out of
``_dashboard.py`` to keep that module under the repo's line-limit.
"""

from __future__ import annotations

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register_start_dashboard(ecosystem) -> None:
    """Wire `start-dashboard` onto the `ecosystem` group."""

    @ecosystem.command(
        "start-dashboard",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Launch the ecosystem dashboard web UI.",
            description=(
                "Serves the Dash app on --host/--port (default "
                "0.0.0.0:8050) and opens a browser unless --no-browser. "
                "With --background the log and pid land under "
                "~/.scitex/dev/runtime/ instead of the foreground.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem start-dashboard",
                    "Serve on 0.0.0.0:8050 and open a browser.",
                ),
                Example(
                    "{prog} ecosystem start-dashboard --port 9000 --background",
                    "Detach on another port.",
                ),
                Example(
                    "{prog} ecosystem start-dashboard --dry-run",
                    "Print what would be done.",
                ),
            ),
        ),
    )
    @click.option("--port", default=8050, type=int, help="Port to serve on.")
    @click.option("--host", default="0.0.0.0", help="Host to bind to.")
    @click.option("--debug", is_flag=True, help="Enable debug/reload mode.")
    @click.option(
        "--no-browser", is_flag=True, help="Do not open browser automatically."
    )
    @click.option("--force", is_flag=True, help="Kill existing process on the port.")
    @click.option(
        "--background", is_flag=True, help="Run dashboard in a background process."
    )
    @click.option(
        "--dry-run", is_flag=True, help="Print what would be done; do not start."
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def ecosystem_start_dashboard(
        port, host, debug, no_browser, force, background, dry_run, yes
    ):
        del yes  # accepted for §2; dashboard launch is non-interactive
        if dry_run:
            click.echo(
                f"would launch dashboard on {host}:{port} "
                f"(background={background}, debug={debug}, force={force})"
            )
            return
        if background:
            # Delegate to run_background so log + pid land under
            # ~/.scitex/dev/runtime/ per 01_arch_06_local-state-directories.md.
            from ....dashboard.app import run_background

            run_background(host=host, port=port, force=force)
            click.echo(f"Dashboard started in background on {host}:{port}")
        else:
            from ....dashboard import run_dashboard

            run_dashboard(
                port=port,
                host=host,
                debug=debug,
                open_browser=not no_browser,
                force=force,
            )


# EOF
