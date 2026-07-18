#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `dashboard` group + `list / start / start-tui / export` subs.

Also hosts the back-compat shims `ecosystem dashboard` (deprecated bare-noun
that prints a redirect and exits 2) and `ecosystem start-dashboard` (web UI
entry point). Both are kept here because they're dashboard-related; they're
intentionally back-compat shims, not new surface.

Thin orchestrator: the ssh remote-render path, the `export` leaf and the
`start-dashboard` web shim live in the `_dashboard_{remote,export,web}`
siblings so this module stays under the repo line-limit.
"""

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup
from ._dashboard_export import register_export
from ._dashboard_remote import render_remote_dashboard
from ._dashboard_web import register_start_dashboard


def register(ecosystem):
    # Back-compat shim: the deprecated bare-noun command must be registered
    # BEFORE the live `dashboard` Group below so the Group definition
    # overrides it as the resolved command (Click later-wins on same name).
    @ecosystem.command(
        "dashboard",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def ecosystem_dashboard_deprecated(ctx):
        """(deprecated) Renamed to `start-dashboard`."""
        click.echo(
            "error: `scitex-dev ecosystem dashboard` was renamed to "
            "`scitex-dev ecosystem start-dashboard`.\n"
            "Re-run with: scitex-dev ecosystem start-dashboard [...]",
            err=True,
        )
        ctx.exit(2)

    @ecosystem.group(
        "dashboard",
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Ecosystem health dashboard (TUI / GUI / export).",
            description=(
                "Subcommands: `list` is a one-shot snapshot table (good "
                "for piping / `watch`); `start` is a live-refresh TUI (or "
                "--gui for the Dash web view); `start-tui` is the "
                "htop-style filterable TUI; `export` is a "
                "machine-readable dump (json / csv / md / org / pdf).",
                "The verbosity flag (-v / -vv / -vvv) controls column "
                "count across all of them. -vvv pulls every cached field; "
                "the same data layer (`gather_ecosystem_state`) feeds "
                "every surface.",
            ),
        ),
    )
    def dashboard():
        pass

    @dashboard.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="One-shot snapshot table of ecosystem state.",
            description=(
                "Live ecosystem dashboard. Visible columns at the current "
                "verbosity are always computed (verbosity != depth); cells "
                "fill in via `rich.live.Live` first-come-first-served as "
                "each future completes — PyPI HTTP, gh-api CI (one GraphQL "
                "batch), audit (one `audit-all` subprocess).",
            ),
            examples=(
                Example(
                    "{prog} ecosystem dashboard list -vv", "More columns."
                ),
                Example(
                    "{prog} ecosystem dashboard list --json | jq",
                    "Structured JSON.",
                ),
                Example(
                    "{prog} ecosystem dashboard list --host spartan",
                    "Inspect a remote's checkouts.",
                ),
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
    @click.option("--package", "-p", multiple=True, help="Limit to specific packages.")
    @click.option(
        "--jobs",
        "-j",
        "jobs",
        default=16,
        show_default=True,
        type=int,
        help=(
            "Concurrent worker threads. All enrichment tasks "
            "(pypi + deep + ci + audit at -vvv) share one pool — "
            "264 tasks for the full ecosystem. Bump to 32-64 to "
            "shorten -vvv wall-clock; cap by GitHub API rate-limit "
            "(~5000/hr) and local CPU."
        ),
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help="Emit JSON instead of the Rich table (alias for `dashboard export --format json`).",
    )
    @click.option(
        "--json-stream",
        is_flag=True,
        hidden=True,
        help=(
            "Internal: emit one JSON snapshot per line as enrichers "
            "complete (newline-delimited JSON of the full state list). "
            "Used by `--host` to render remote progress incrementally."
        ),
    )
    @click.option(
        "--with-tests",
        type=click.Choice(["off", "collect", "run"]),
        default="off",
        show_default=True,
        help=(
            "Populate the pytest column with real data:  "
            "`off` (default) shows the cheap test-file count;  "
            "`collect` runs `pytest --collect-only` per pkg "
            "(~3-10s/pkg) and shows the parametrize-aware test count;  "
            "`run` actually runs pytest per pkg (~30-300s each) and "
            "shows `F<failed> (<passed>/<total>)` with the F red on "
            "failures. Both `collect` and `run` invoke pytest INSIDE "
            "each pkg's `<pkg>/.venv/` and skip pkgs whose venv is a "
            "symlink or missing."
        ),
    )
    @click.option(
        "--host",
        default=None,
        help=(
            "SSH host whose ~/proj/ checkouts should be inspected "
            "instead of the local machine's. Useful when active "
            "development has moved to a remote (e.g. Spartan) so the "
            "local clones drift behind. Requires `scitex-dev` "
            "installed on the remote. Implementation: ssh runs "
            "`scitex-dev ecosystem dashboard list --json [flags]` on "
            "the remote, the result is deserialised and rendered with "
            "the local renderer."
        ),
    )
    def dashboard_list(
        verbosity, package, jobs, as_json, json_stream, with_tests, host
    ):
        import time

        from .._dashboard import gather_ecosystem_state
        from .._dashboard._render import (
            cols_for_verbosity,
            enrichers_for_cols,
            render_table,
        )

        # --host: shell out to remote scitex-dev for the JSON payload,
        # deserialise into PackageState objects, then render locally.
        # Lets a developer working on Spartan see Spartan's clone state
        # from a local terminal without re-implementing the gatherer
        # over ssh.
        if host:
            render_remote_dashboard(
                host=host,
                verbosity=verbosity,
                packages=list(package),
                jobs=jobs,
                with_tests=with_tests,
                as_json=as_json,
            )
            return

        cols = cols_for_verbosity(verbosity)
        enrichers = enrichers_for_cols(cols)
        # `--with-tests` opt-ins enrich `tests_collected` / `tests_passed`
        # & `tests_failed` so the pytest column can show the real
        # `F NN (NN/NN)` format instead of just the file count.
        if with_tests == "collect":
            enrichers.add("tests-collect")
        elif with_tests == "run":
            enrichers.add("tests-run")

        # `-p` accepts repeats AND comma-separated values, plus the
        # literal `all` (expands to every registered pkg). Mirrors
        # `audit-all`'s argument style.
        #   -p scitex-io -p scitex-stats     → ["scitex-io", "scitex-stats"]
        #   -p scitex-io,scitex-stats        → ["scitex-io", "scitex-stats"]
        #   -p all                           → None (all pkgs)
        raw_pkgs: list[str] = []
        for entry in package:
            raw_pkgs.extend(p.strip() for p in entry.split(",") if p.strip())
        if "all" in raw_pkgs:
            packages_arg: list[str] | None = None
        elif raw_pkgs:
            seen: set[str] = set()
            packages_arg = []
            for p in raw_pkgs:
                if p not in seen:
                    seen.add(p)
                    packages_arg.append(p)
        else:
            packages_arg = None

        if json_stream:
            # Emit one JSON snapshot per line as enrichers complete.
            # Used by --host to stream remote progress incrementally.
            import json as _json
            import sys as _sys

            def _emit(states):
                _sys.stdout.write(
                    _json.dumps([s.to_dict() for s in states], default=str)
                )
                _sys.stdout.write("\n")
                _sys.stdout.flush()

            gather_ecosystem_state(
                verbosity=verbosity,
                packages=packages_arg,
                workers=jobs,
                on_update=_emit,
                enrichers=enrichers,
            )
            return

        if as_json:
            states = gather_ecosystem_state(
                verbosity=verbosity,
                packages=packages_arg,
                workers=jobs,
                enrichers=enrichers,
            )
            from .._dashboard import _export as exp

            click.echo(exp.to_json(states))
            return

        from rich.console import Console
        from rich.live import Live

        console = Console()

        # Always live-stream. Even at v=0/1 we may have audit/pypi/CI
        # columns visible that need computation; the basic gather is
        # sub-second so Live engagement cost is negligible.
        last_paint = [0.0]
        states_box: list = []

        def _on_update(states):
            states_box[:] = states
            now = time.monotonic()
            if now - last_paint[0] >= 1.0:
                live.update(render_table(states, verbosity=verbosity))
                last_paint[0] = now

        with Live(
            render_table([], verbosity=verbosity),
            console=console,
            refresh_per_second=2,
            transient=False,
            screen=True,
        ) as live:
            gather_ecosystem_state(
                verbosity=verbosity,
                packages=packages_arg,
                workers=jobs,
                on_update=_on_update,
                enrichers=enrichers,
            )
            # Final paint to ensure the last-completion delta lands.
            live.update(render_table(states_box, verbosity=verbosity))

        console.print(render_table(states_box, verbosity=verbosity))

    @dashboard.command(
        "start",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Live-refresh dashboard. TUI by default; --gui for the web view.",
            examples=(
                Example("{prog} ecosystem dashboard start -vv", "More columns."),
                Example(
                    "{prog} ecosystem dashboard start --gui",
                    "Dash web view (deferred).",
                ),
                Example(
                    "{prog} ecosystem dashboard start --interval 10",
                    "Refresh every 10s.",
                ),
            ),
        ),
    )
    @click.option("-v", "verbosity", count=True, default=1)
    @click.option(
        "--gui", is_flag=True, help="Launch the Dash web view at 127.0.0.1:8050."
    )
    @click.option(
        "--interval", type=float, default=5.0, help="TUI refresh interval (seconds)."
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print refresh plan (verbosity, interval, package count) and exit without rendering.",
    )
    @click.option(
        "-y",
        "--yes",
        "yes",
        is_flag=True,
        help="No-op confirmation flag retained for §2 audit-cli compliance.",
    )
    def dashboard_start(verbosity, gui, interval, dry_run, yes):
        if dry_run:
            click.echo(
                f"would render: verbosity={verbosity} interval={interval}s "
                f"gui={'yes' if gui else 'no'}"
            )
            return
        del yes  # accepted for compliance; nothing to confirm
        if gui:
            click.echo(
                "error: --gui (Dash web view) is not yet wired into the v0 dashboard.\n"
                "       Use `dashboard list` for a snapshot or `dashboard export` for a dump.",
                err=True,
            )
            raise SystemExit(2)

        from rich.console import Console
        from rich.live import Live

        from .._dashboard import gather_ecosystem_state
        from .._dashboard._render import render_table

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

    @dashboard.command(
        "start-tui",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="htop-style TUI with live keystroke filter.",
            description=(
                "Requires the optional `textual` package "
                "(`pip install textual`).",
                "Keys: `/` start filter; Escape clear filter; `r` refresh "
                "data; `q` quit; `j`/`k` or down/up navigate rows; `g` / "
                "`G` jump to top / bottom.",
            ),
            examples=(
                Example("{prog} ecosystem dashboard start-tui", "Launch the TUI."),
                Example(
                    "{prog} ecosystem dashboard start-tui -p scitex-io,scitex-stats",
                    "Limit to two packages.",
                ),
                Example("{prog} ecosystem dashboard start-tui -vv", "More columns."),
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
        help="Print plan (verbosity, package count) and exit without launching the TUI.",
    )
    @click.option(
        "-y",
        "--yes",
        "yes",
        is_flag=True,
        help="No-op confirmation flag retained for §2 audit-cli compliance.",
    )
    def dashboard_tui(verbosity, package, jobs, dry_run, yes):
        raw_pkgs: list[str] = []
        for entry in package:
            raw_pkgs.extend(p.strip() for p in entry.split(",") if p.strip())
        if "all" in raw_pkgs:
            packages_arg: list[str] | None = None
        elif raw_pkgs:
            seen: set[str] = set()
            packages_arg = []
            for p in raw_pkgs:
                if p not in seen:
                    seen.add(p)
                    packages_arg.append(p)
        else:
            packages_arg = None

        del yes  # accepted for §2 compliance
        if dry_run:
            n = len(packages_arg) if packages_arg else "all"
            click.echo(
                f"would launch TUI: verbosity={verbosity} packages={n} jobs={jobs}"
            )
            return

        try:
            from .._dashboard._tui import run_tui
        except ImportError as exc:
            click.echo(f"error: {exc}", err=True)
            raise SystemExit(2)

        try:
            run_tui(verbosity=verbosity, packages=packages_arg, workers=jobs)
        except ImportError as exc:
            click.echo(f"error: {exc}", err=True)
            raise SystemExit(2)

    register_export(dashboard)

    # Back-compat shim: web UI entry point. Kept dashboard-adjacent; the
    # `start-dashboard` name predates the `dashboard` group and is
    # preserved for external scripts/CI.
    register_start_dashboard(ecosystem)


# EOF
