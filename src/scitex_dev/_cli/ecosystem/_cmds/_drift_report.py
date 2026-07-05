#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `drift-report` — unified per-package × per-layer version matrix.

Thin CLI surface (mirrors ``_versions.py``'s ``register(ecosystem)`` and
``check-versions``' option conventions). All logic lives in the
``scitex_dev._ecosystem._drift_report`` engine package; this module only
wires options, prints, and sets the observe-mode exit code (0 = no drift,
1 = drift), so it is usable as a scheduled gate.
"""

import json

import click


def register(ecosystem):
    @ecosystem.command("drift-report")
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
        """Report version drift across all 8 layers, package × layer.

        \b
        Layers: PyPI, GitHub (release tag), each host's develop checkout,
        container base image + agent overlay (via `sac versions --json`),
        CI (not-collected in v1), and the editable/installed version. The
        SSoT is `pyproject.toml` on the local develop checkout; any cell
        that disagrees is flagged with `*`. Exit 1 iff drift is detected.

        \b
        Example:
            $ scitex-dev ecosystem drift-report
            $ scitex-dev ecosystem drift-report -p scitex-io --json
            $ scitex-dev ecosystem drift-report -h spartan -q
        """
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

        # Observe-mode exit semantics (mirrors check-versions): drift → 1.
        ctx.exit(1 if matrix.has_drift else 0)
