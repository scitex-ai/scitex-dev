#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem run`` — the collective ecosystem supervisor.

This is the ``ExecStart`` of ``scitex-dev-ecosystem.service`` (operator
policy 2026-06-14: the SOLE systemd ``--user`` entry for the SciTeX
fleet). Long-running foreground process; foreground because systemd
``Type=simple`` expects ExecStart to not double-fork — and because
``journalctl --user -u scitex-dev-ecosystem`` then picks up the
supervisor's stdout/stderr without any extra wiring.

The command itself is intentionally thin — almost all the work lives
in :func:`scitex_dev._supervisor.run_supervisor`. Keeping the CLI as a
thin shim means a future ``--config-file`` / ``--once`` / ``--dry-run``
option lands here without disturbing the loop body.

Backwards compat
----------------
This command is NEW in PR-1 of the supervisor migration; no prior
``ecosystem run`` existed, so we have no historical args to maintain.
"""

from __future__ import annotations

import logging
import sys

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ...._supervisor import run_supervisor


def register(ecosystem):
    @ecosystem.command(
        "run",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Run the SciTeX ecosystem supervisor (Type=simple, foreground).",
            description=(
                "Backed by scitex_dev._supervisor.run_supervisor; that "
                "module's docstring documents the tick budget, signal-"
                "handling, hot-reload (SIGHUP), and the state-file "
                "path. This is what systemd invokes via "
                "scitex-dev-ecosystem.service's ExecStart — foreground, "
                "because Type=simple expects ExecStart to not "
                "double-fork, and because journalctl --user -u "
                "scitex-dev-ecosystem then picks up stdout/stderr "
                "without extra wiring.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem run",
                    "Run forever (what systemd invokes).",
                ),
                Example(
                    "{prog} ecosystem run --max-ticks 3",
                    "Smoke-test path: 3 ticks then exit.",
                ),
            ),
        ),
    )
    @click.option(
        "--max-ticks",
        type=int,
        default=None,
        help=(
            "Stop after N ticks instead of looping forever. Test seam — "
            "production omits this and the supervisor runs until SIGTERM."
        ),
    )
    @click.option(
        "-v",
        "--verbose",
        is_flag=True,
        help=(
            "Set the supervisor's log level to DEBUG (default WARNING). "
            "The supervisor's diagnostics go to stdout/stderr → captured "
            "by systemd into journalctl."
        ),
    )
    def ecosystem_run(max_ticks, verbose):
        # Configure logging on the way in. systemd Type=simple captures
        # stdout + stderr into the journal, so logging.basicConfig with
        # the default stderr handler is correct here — no journal-specific
        # handler needed.
        logging.basicConfig(
            level=logging.DEBUG if verbose else logging.WARNING,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            stream=sys.stderr,
        )
        rc = run_supervisor(max_ticks=max_ticks)
        sys.exit(rc)


__all__ = ["register"]


# EOF
