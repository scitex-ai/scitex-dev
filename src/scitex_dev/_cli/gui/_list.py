#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev gui list` — one-shot ecosystem state table.

Moved verbatim from `ecosystem dashboard list` when §12's canonical
`gui` group landed; the old path still works through the Phase W alias
in `_aliases.py`.
"""

from __future__ import annotations

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ._shared import render_remote, resolve_packages

__all__ = ["register"]


def register(gui: click.Group) -> None:
    @gui.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="One-shot ecosystem state table (pipe- and watch-friendly).",
            description=(
                "Visible columns at the current verbosity are always "
                "computed (verbosity is breadth, not depth); cells fill in "
                "live as each future completes — PyPI HTTP, gh-api CI (one "
                "GraphQL batch), audit (one `audit-all` subprocess)."
            ),
            examples=(
                Example("{prog} gui list -vv", "More columns."),
                Example("{prog} gui list --json | jq", "Machine-readable snapshot."),
                Example("{prog} gui list --host spartan", "Inspect a remote checkout."),
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
            "264 tasks for the full ecosystem. Bump to 32-64 to shorten "
            "-vvv wall-clock; cap by GitHub API rate-limit (~5000/hr) "
            "and local CPU."
        ),
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help=(
            "Emit JSON instead of the Rich table "
            "(alias for `gui export --format json`)."
        ),
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
            "SSH host whose ~/proj/ checkouts should be inspected instead "
            "of the local machine's. Useful when active development has "
            "moved to a remote (e.g. Spartan) so the local clones drift "
            "behind. Requires a scitex-dev on the remote new enough to "
            "have the `gui` group; implementation: ssh runs `scitex-dev "
            "gui list --json-stream [flags]` there, the result is "
            "deserialised and rendered with the local renderer."
        ),
    )
    def gui_list(verbosity, package, jobs, as_json, json_stream, with_tests, host):
        import time

        from ..ecosystem._dashboard import gather_ecosystem_state
        from ..ecosystem._dashboard._render import (
            cols_for_verbosity,
            enrichers_for_cols,
            render_table,
        )

        # --host: shell out to a remote scitex-dev for the JSON payload,
        # deserialise into PackageState objects, then render locally.
        if host:
            render_remote(
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

        packages_arg = resolve_packages(package)

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
            from ..ecosystem._dashboard import _export as exp

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


# EOF
