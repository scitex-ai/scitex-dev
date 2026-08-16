#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/ecosystem/_cmds/_list_exemptions.py

"""ecosystem `list-exemptions` — every audit exemption in the fleet, in one place.

WHY THIS EXISTS. Operator, 2026-08-16: 「例外として leaf 固有の workflow を
認める; 例外はこちらで把握できるようにする」 — leaf-specific exceptions are
PERMITTED, and the exceptions must be graspable centrally.

The declaring half already worked: each exemption lives in its own repo's
`.scitex/dev/config.yaml`, per-file, with a mandatory written reason. The
SEEING half did not exist, because those files sit in ~70 separate
repositories. Nobody could answer "how many exceptions exist, where, and why"
without opening 70 files, so in practice nobody asked — and an exception
nobody can see is an exception that never gets retired. Permission without
visibility is not a policy, it is a leak.

WHAT THIS PRINTS THAT A NAIVE VERSION WOULD NOT
------------------------------------------------
Measured on scitex-compute-04, 2026-08-16: only **18 of the 70** registered
packages are checked out on this host. A census that silently skipped the
other 52 would report a total that LOOKS fleet-wide and is not — and it would
err in the reassuring direction, which is the worst direction available to an
exception register. The number would shrink as checkouts went missing, and
shrinking looks like progress.

So `unreadable` is printed as a first-class part of the answer, and the total
is never called a fleet total unless every package was actually consulted.
The distinction the output preserves:

    declared    read the config, found an exemption
    clean       read the config, found none
    unread      could not consult the config at all  <- NOT the same as clean

`unread` is the one a summary would drop, and it is the one that decides
whether the other two numbers mean anything.
"""

from __future__ import annotations

import json

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def build_report(census, packages_total: int) -> dict:
    """Shape the census into the declared JSON payload.

    Split from the printer so the shape is testable without click, and so
    `--json` and the human rendering can never disagree about the counts:
    both read this one dict.
    """
    return {
        "complete": census.is_complete,
        "packages_total": packages_total,
        "packages_read": len(census.clean)
        + len({row.package for row in census.exemptions}),
        "packages_unread": len(census.unreadable),
        "exemptions_found": census.total_declared,
        "exemptions": [
            {
                "package": row.package,
                "rule": row.rule,
                "path": row.path,
                "line": row.line,
                "reason": row.reason,
            }
            for row in census.exemptions
        ],
        "clean": list(census.clean),
        "unreadable": [
            {"package": pkg, "why": why} for pkg, why in census.unreadable
        ],
    }


def _emit_human(report: dict, echo) -> None:
    """Render the report for a human, incompleteness first-class.

    The header states what was READ before it states what was FOUND. A count
    presented ahead of its own coverage invites the reader to treat it as the
    whole, which is exactly the misreading this command exists to prevent.
    """
    read = report["packages_read"]
    total = report["packages_total"]
    found = report["exemptions_found"]

    echo(
        f"read {read} of {total} package(s); "
        f"{found} exemption(s) declared in what was read"
    )

    by_package: dict[str, list[dict]] = {}
    for row in report["exemptions"]:
        by_package.setdefault(row["package"], []).append(row)

    for pkg in sorted(by_package):
        echo("")
        echo(pkg)
        for row in sorted(by_package[pkg], key=lambda r: (r["path"], r["line"])):
            echo(f"  {row['rule']}  {row['path']}:{row['line']}")
            echo(f"      {row['reason']}")

    if not report["complete"]:
        unread = report["packages_unread"]
        echo("")
        echo(
            f"INCOMPLETE: {unread} package(s) could NOT be consulted, so "
            f"{found} is NOT a fleet-wide count.",
            err=True,
        )
        for row in report["unreadable"]:
            echo(f"  {row['package']}: {row['why']}", err=True)
        echo(
            "Check those out (or run this where they live) before quoting a "
            "fleet total.",
            err=True,
        )


def register(ecosystem):
    @ecosystem.command(
        "list-exemptions",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List every declared audit exemption across the ecosystem.",
            description=(
                "Reads each registered package's `.scitex/dev/config.yaml` and "
                "prints the exemptions it declares, with the rule, the exact "
                "site, and the written reason. Packages that could not be "
                "consulted at all — not checked out here, no local_path, "
                "unreadable config — are reported SEPARATELY from packages "
                "that were read and declare none, because 'no exemptions' and "
                "'never asked' are different answers and only one of them is "
                "good news. When any package is unread the totals are labelled "
                "incomplete rather than presented as fleet-wide."
            ),
            examples=(
                Example(
                    "{prog} ecosystem list-exemptions",
                    "List every exemption that can be read from here.",
                ),
                Example(
                    "{prog} ecosystem list-exemptions --json",
                    "Machine-readable payload, same counts as the human view.",
                ),
                Example(
                    "{prog} ecosystem list-exemptions --package scitex-io",
                    "Restrict to named packages (repeatable).",
                ),
            ),
        ),
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help="Emit the declared JSON payload instead of the human view.",
    )
    @click.option(
        "--package",
        "packages",
        multiple=True,
        help="Only consult these packages (repeatable). Default: all.",
    )
    def ecosystem_list_exemptions(as_json, packages):
        from ...._ecosystem import ECOSYSTEM
        from ...._ecosystem._exemption_census import collect_exemptions
        from ...audit._config._loader import load_config

        selected = list(packages) or None
        census = collect_exemptions(
            ECOSYSTEM, load_config=load_config, packages=selected
        )
        total = len(selected) if selected else len(ECOSYSTEM)
        report = build_report(census, total)

        if as_json:
            click.echo(json.dumps(report, indent=2, sort_keys=True))
            return

        def echo(text: str = "", err: bool = False) -> None:
            click.echo(text, err=err)

        _emit_human(report, echo)


# EOF
