#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `gui` group -- fan-out launcher for the leaf-package GUIs.

Distinct from the top-level `scitex-dev gui` group (scitex-dev's OWN
dashboard): this `ecosystem gui` group opens the OTHER leaf packages'
browser GUIs (todo board, live-paper, storage, figrecipe, scholar,
writer) at once. Ports come from the scitex-dev-owned SSOT
``scitex_dev._ecosystem.gui_registry``.
"""

from __future__ import annotations

import json
import webbrowser

import click

from ...._ecosystem.gui_registry import RESERVED_PORTS, gui_surfaces
from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def _audit_findings():
    """Return GUI-port fan-out findings as a list of dicts.

    Two check classes, each finding a fixed shape
    ``{package, kind, severity, actual, target, detail}``:

    - ``reservation-violation`` (severity ``error``): a surface's
      ``target_port`` is not reserved to that package in
      ``RESERVED_PORTS`` -- a bad registry edit that would re-collide
      with another service. Should never fire on a correct registry.
    - ``pending-migration`` (severity ``warning``): the leaf still
      binds ``actual_port`` != its assigned ``target_port`` -- the
      leaf fan-out has not landed yet (e.g. cards 8051 -> 31299,
      live-paper 8765 -> 31300).
    """
    findings = []
    for s in gui_surfaces():
        owner = RESERVED_PORTS.get(s.target_port)
        if owner != s.package:
            findings.append(
                {
                    "package": s.package,
                    "kind": "reservation-violation",
                    "severity": "error",
                    "actual": s.actual_port,
                    "target": s.target_port,
                    "detail": (
                        f"target {s.target_port} is reserved to "
                        f"{owner or '<unreserved>'}, not {s.package}"
                    ),
                }
            )
        elif s.actual_port != s.target_port:
            findings.append(
                {
                    "package": s.package,
                    "kind": "pending-migration",
                    "severity": "warning",
                    "actual": s.actual_port,
                    "target": s.target_port,
                    "detail": (
                        f"{s.package} still binds {s.actual_port}; "
                        f"assigned target is {s.target_port}"
                    ),
                }
            )
    return findings


def register(ecosystem):
    @ecosystem.group(
        "gui",
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Open the leaf-package browser GUIs (fan-out launcher).",
            description=(
                "Fan-out launcher for the OTHER SciTeX leaf packages' "
                "browser GUIs (todo board, live-paper, storage, figrecipe, "
                "scholar, writer). Ports come from the scitex-dev-owned "
                "3129X port-registry SSOT. This is NOT scitex-dev's own "
                "dashboard -- that is the top-level `gui` group."
            ),
            examples=(
                Example("{prog} ecosystem gui list", "Table of every leaf GUI + URL."),
                Example("{prog} ecosystem gui open", "Open every leaf GUI in a browser tab."),
            ),
        ),
    )
    def gui():
        pass

    @gui.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List the leaf-package GUIs (package, ports, URL).",
            examples=(
                Example("{prog} ecosystem gui list", "Table of package, ports, URL."),
                Example("{prog} ecosystem gui list --json", "Structured JSON output."),
            ),
        ),
    )
    @click.option("--host", default="localhost", show_default=True, help="URL host.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def gui_list(host, as_json):
        surfaces = gui_surfaces()
        if as_json:
            items = [
                {
                    "package": s.package,
                    "actual_port": s.actual_port,
                    "target_port": s.target_port,
                    "path": s.path,
                    "url": s.url(host=host),
                }
                for s in surfaces
            ]
            click.echo(json.dumps({"surfaces": items}))
            return

        header = f"  {'PACKAGE':22s} {'ACTUAL':>7s} {'TARGET':>7s}  URL"
        click.echo(header)
        for s in surfaces:
            click.echo(
                f"  {s.package:22s} {s.actual_port:>7d} {s.target_port:>7d}  "
                f"{s.url(host=host)}"
            )

    @gui.command(
        "open",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Open browser tab(s) for the named leaf GUIs (or all).",
            description=(
                "Opens a browser tab for each named package (or every leaf "
                "GUI when none are named), using the ACTUAL live port. "
                "Best-effort via webbrowser.open; each URL is printed. Use "
                "--dry-run to print the URLs without opening a browser."
            ),
            examples=(
                Example("{prog} ecosystem gui open", "Open every leaf GUI."),
                Example("{prog} ecosystem gui open scitex-writer", "Open one package."),
                Example("{prog} ecosystem gui open --dry-run", "Print URLs, open nothing."),
            ),
        ),
    )
    @click.argument("packages", nargs=-1)
    @click.option("--host", default="localhost", show_default=True, help="URL host.")
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the URLs without opening a browser.",
    )
    def gui_open(packages, host, dry_run):
        surfaces = gui_surfaces()
        by_name = {s.package: s for s in surfaces}

        if packages:
            unknown = [p for p in packages if p not in by_name]
            if unknown:
                known = ", ".join(sorted(by_name))
                raise click.UsageError(
                    f"unknown package(s): {', '.join(unknown)} — known: {known}"
                )
            selected = [by_name[p] for p in packages]
        else:
            selected = surfaces

        for s in selected:
            target = s.url(host=host)
            if dry_run:
                click.echo(target)
            else:
                click.echo(f"opening {s.package}: {target}")
                webbrowser.open(target)

    @gui.command(
        "audit",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Audit each leaf GUI's port against the registry SSOT.",
            description=(
                "Fan-out auditor for the 3129X/3130X GUI port scheme. "
                "Reports two finding classes: 'reservation-violation' "
                "(a target port is not reserved to that package -- a bad "
                "registry edit that would re-collide with another "
                "service) and 'pending-migration' (a leaf still binds its "
                "old actual port instead of its assigned target, e.g. "
                "cards 8051->31299). Exits non-zero when any finding "
                "exists so it CAN gate CI once the leaf fan-out lands; it "
                "is a diagnostic today, not wired into the blocking CI "
                "matrix (develop must not go red on known-pending "
                "migrations)."
            ),
            examples=(
                Example("{prog} ecosystem gui audit", "Report GUI-port drift."),
                Example("{prog} ecosystem gui audit --json", "Structured JSON output."),
            ),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def gui_audit(as_json):
        findings = _audit_findings()
        n_errors = sum(1 for f in findings if f["severity"] == "error")
        exit_code = 1 if findings else 0

        if as_json:
            click.echo(
                json.dumps(
                    {
                        "findings": findings,
                        "errors": n_errors,
                        "exit_code": exit_code,
                    }
                )
            )
            raise SystemExit(exit_code)

        if not findings:
            click.echo("gui audit: all leaf GUI ports conform to the registry.")
            raise SystemExit(exit_code)

        click.echo(f"gui audit: {len(findings)} finding(s) ({n_errors} error)")
        for f in findings:
            click.echo(
                f"  [{f['severity']:7s}] {f['package']:20s} {f['kind']:22s} "
                f"actual={f['actual']} target={f['target']} — {f['detail']}"
            )
        raise SystemExit(exit_code)
