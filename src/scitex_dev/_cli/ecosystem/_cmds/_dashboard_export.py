#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`ecosystem dashboard export` — machine-readable dashboard dumps.

Split out of ``_dashboard.py`` to keep that module under the repo's
line-limit. The org/pdf branch (the "usual PDF" convention) is the bulk
of it and is independent of the live-render commands.
"""

from __future__ import annotations

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register_export(dashboard) -> None:
    """Wire `export` onto the `dashboard` group."""

    @dashboard.command(
        "export",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Machine-readable dump of the dashboard state.",
            description=(
                "Defaults to -vvv (all columns). For the `md` / `org` / "
                "`pdf` formats the gh-release enricher is forced on (and "
                "`pypi` below -vv) so the RELEASE and PYPI columns carry "
                "real data rather than N/C.",
                "`org` emits a ywatanabe-convention Org-mode report — the "
                "'usual PDF' source; `pdf` runs the org->pdf convert via "
                "pandoc / `emacs --batch` and writes the .pdf plus its "
                ".org sidecar to the path given by --output.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem dashboard export --format json | jq",
                    "Pipe JSON to jq.",
                ),
                Example(
                    "{prog} ecosystem dashboard export --format csv > state.csv",
                    "Spreadsheet dump.",
                ),
                Example(
                    "{prog} ecosystem dashboard export --format md",
                    "Paste into README.",
                ),
                Example(
                    "{prog} ecosystem dashboard export --format org > report.org",
                    "Org-mode report.",
                ),
                Example(
                    "{prog} ecosystem dashboard export --format pdf -o report.pdf",
                    "PDF (+ .org sidecar).",
                ),
            ),
        ),
    )
    @click.option(
        "--format",
        "fmt",
        type=click.Choice(["json", "csv", "md", "org", "pdf"]),
        default="json",
        help=(
            "Output format. `org` emits a ywatanabe-convention Org-mode "
            "report (the 'usual PDF' source); `pdf` runs the org→pdf "
            "convert via pandoc / `emacs --batch` and writes the .pdf "
            "(+ .org sidecar) to the path given by --output."
        ),
    )
    @click.option(
        "-v",
        "verbosity",
        count=True,
        default=3,
        help="Default -vvv (all columns) for export.",
    )
    @click.option("--package", "-p", multiple=True)
    @click.option(
        "--output",
        "-o",
        "output",
        default=None,
        type=click.Path(),
        help=(
            "Output file path (required for --format pdf; optional for "
            "other formats — defaults to stdout). For pdf the .org "
            "sidecar is written next to the .pdf with the same stem."
        ),
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print row count + format that would be emitted; no payload written.",
    )
    @click.option(
        "-y",
        "--yes",
        "yes",
        is_flag=True,
        help="No-op confirmation flag retained for §2 audit-cli compliance.",
    )
    def dashboard_export(fmt, verbosity, package, output, dry_run, yes):
        from pathlib import Path

        from .._dashboard import _export as exp
        from .._dashboard import gather_ecosystem_state
        from .._dashboard._render import (
            cols_for_verbosity,
            enrichers_for_cols,
        )

        # Make sure the gh-release enricher always runs for org/pdf/md
        # exports so the RELEASE column has real data. The export CLI
        # defaults to -vvv, but `gather_ecosystem_state`'s verbosity →
        # enrichers heuristic doesn't include `gh-release` (it's only
        # added by `dashboard list` based on visible columns). Without
        # this, reports always show N/C for GH-Release, defeating the
        # point of the column.
        enrichers = enrichers_for_cols(cols_for_verbosity(verbosity))
        if fmt in ("md", "org", "pdf"):
            enrichers.add("gh-release")
            if verbosity < 2:
                enrichers.add("pypi")  # PYPI column also needs network

        states = gather_ecosystem_state(
            verbosity=verbosity,
            packages=list(package) or None,
            enrichers=enrichers,
        )
        if dry_run:
            click.echo(
                f"would emit: format={fmt} rows={len(states)} "
                f"verbosity={verbosity}"
                + (f" output={output}" if output else "")
            )
            return
        del yes

        # PDF follows the ywatanabe "usual PDF" convention: the .org
        # is the canonical source and the .pdf is rendered from it by
        # pandoc or `emacs --batch`. PDF therefore needs a filesystem
        # path; everything else can go to stdout if no -o is given.
        if fmt == "pdf":
            if not output:
                # Timestamped default so the operator always gets
                # something usable, even from a redirected stdout.
                from datetime import datetime as _dt

                output = str(
                    Path(
                        f"scitex-ecosystem-"
                        f"{_dt.now().strftime('%Y%m%d-%H%M%S')}.pdf"
                    ).resolve()
                )
            result = exp.to_pdf(states, output)
            if result["status"] == "ok":
                click.echo(
                    f"wrote {result['pdf']} (org sidecar: {result['org']}) "
                    f"via {result['tool']}"
                )
            elif result["status"] == "org_only":
                # Exit 0 — the .org file is still a usable artefact.
                # The 2026-05-27 instructions explicitly say "do not
                # block" when the host lacks the converter.
                click.echo(
                    f"wrote {result['org']} but could not produce PDF: "
                    f"{result['reason']}",
                    err=True,
                )
            else:
                click.echo(
                    f"wrote {result['org']} but {result['tool']} failed: "
                    f"{result.get('error', 'unknown error')}",
                    err=True,
                )
                raise SystemExit(2)
            return

        if fmt == "org":
            text = exp.to_org(states)
        elif fmt == "json":
            text = exp.to_json(states)
        elif fmt == "csv":
            text = exp.to_csv(states)
        elif fmt == "md":
            text = exp.to_markdown(states)
        else:  # pragma: no cover — click.Choice prevents this
            raise click.ClickException(f"unknown format: {fmt}")

        if output:
            Path(output).expanduser().resolve().write_text(text, encoding="utf-8")
            click.echo(f"wrote {output}")
        else:
            click.echo(text)


# EOF
