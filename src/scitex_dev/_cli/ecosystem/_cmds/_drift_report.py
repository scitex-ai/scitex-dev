#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `drift-report` — unified per-package × per-layer version matrix.

Thin CLI surface (mirrors ``_versions.py``'s ``register(ecosystem)`` and
``validate-versions``' option conventions). All logic lives in the
``scitex_dev._ecosystem._drift_report`` engine package; this module only
wires options, prints, and sets the completed-report exit code from
DriftMatrix.has_drift, including missing baselines and install findings.
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
                "Layers: PyPI, reachable tag at origin/main (fallback main), "
                "selected host checkouts, base-image + agent-overlay via "
                "`sac versions --json`, CI (not collected), and the current "
                "interpreter's installed version. The version reference is "
                "committed pyproject.toml at develop (fallback origin/develop), "
                "not the working tree. Independent critical-package staleness "
                "and registry-wide install-integrity checks still run with "
                "matrix filters. Exit 1 on drifting rows, missing reference "
                "versions, critical staleness or untrustworthy installs; "
                "otherwise 0. Unknown cells can leave coverage incomplete. "
                "Use --json for install-integrity details; full/quiet human "
                "renderers do not currently include those details."
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

        # Completed-report verdict includes missing baselines and install findings.
        ctx.exit(1 if matrix.has_drift else 0)
