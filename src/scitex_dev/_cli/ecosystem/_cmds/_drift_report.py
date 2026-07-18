#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `drift-report` — unified per-package × per-layer version matrix.

Thin CLI surface (mirrors ``_versions.py``'s ``register(ecosystem)`` and
``validate-versions``' option conventions). All logic lives in the
``scitex_dev._ecosystem._drift_report`` engine package; this module only
wires options, prints, and sets the observe-mode exit code (0 = no drift,
1 = drift), so it is usable as a scheduled gate.
"""

import json

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(ecosystem):
    @ecosystem.command(
        "drift-report",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Report version drift across all 8 layers, package x layer.",
            description=(
                "Layers: PyPI, GitHub (release tag), each host's develop "
                "checkout, container base image + agent overlay (via "
                "`sac versions --json`), CI (not-collected in v1), and "
                "the editable/installed version. The SSoT is "
                "`pyproject.toml` on the local develop checkout; any "
                "cell that disagrees is flagged with `*`. Also runs an "
                "independent critical-package check (scitex-todo, "
                "scitex-agent-container, scitex-dev) against THIS "
                "interpreter's installs, falling back to PyPI when no "
                "local checkout exists, and prints a LOUD banner ahead "
                "of the matrix when one is behind (closes the silent "
                "gap that let a container run scitex-todo 0.7.28 "
                "unnoticed, 2026-07-12). Exit 1 iff drift is detected.",
            ),
            examples=(
                Example("{prog} ecosystem drift-report", "Full matrix report."),
                Example(
                    "{prog} ecosystem drift-report -p scitex-io --json",
                    "One package, as JSON.",
                ),
                Example(
                    "{prog} ecosystem drift-report -h spartan -q",
                    "One host, one-line summary.",
                ),
            ),
        ),
    )
    @click.option(
        "--host",
        "-h",
        "hosts",
        multiple=True,
        help="Host name(s). Default: all enabled hosts.",
    )
    @click.option(
        "--package",
        "-p",
        "packages",
        multiple=True,
        help="Package name(s). Default: all.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.option(
        "--quiet",
        "-q",
        is_flag=True,
        help="Emit a one-line summary instead of the full matrix.",
    )
    @click.pass_context
    def ecosystem_drift_report(ctx, hosts, packages, as_json, quiet):
        from ...._ecosystem._drift_report import (
            collect_drift_matrix,
            render_quiet,
            render_report,
        )

        host_list = list(hosts) if hosts else None
        pkg_list = list(packages) if packages else None
        if host_list == ["all"]:
            host_list = None

        matrix = collect_drift_matrix(packages=pkg_list, hosts=host_list)

        if as_json:
            click.echo(json.dumps(matrix.to_dict(), indent=2, default=str))
        elif quiet:
            click.echo(render_quiet(matrix))
        else:
            click.echo(render_report(matrix))

        # Observe-mode exit semantics (mirrors validate-versions): drift → 1.
        ctx.exit(1 if matrix.has_drift else 0)
