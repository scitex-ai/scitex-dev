#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared `status` / `enable` / `disable` knob subcommands.

Attached to BOTH the `skills` and `mcp` command groups so scitex-dev can
centrally toggle each package's progressive-disclosure knob (operator
2026-07-20). The verbs are `status` (not `list` — the skills group already
has `list` for the corpus, mcp has `list-tools`), `enable <package>`, and
`disable <package>`. Toggles persist to the machine-managed knob-state file
via `set_package_knob`; config.yaml is never rewritten.
"""

from __future__ import annotations

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand


def add_knob_commands(group: click.Group, kind: str) -> click.Group:
    """Attach `status` / `enable` / `disable` for the ``kind`` knob to *group*.

    ``kind`` is ``"skills"`` or ``"mcp"``.
    """
    from .._core.config import load_config, set_package_knob

    def _is_enabled(pkg) -> bool:
        return pkg.skills_enabled if kind == "skills" else pkg.mcp_enabled

    @group.command(
        "status",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary=f"Show each package's {kind}-enabled knob state.",
            examples=(
                Example("{prog} " + f"{kind} status", f"Per-package {kind} on/off."),
                Example("{prog} " + f"{kind} status --json", "Structured JSON."),
            ),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def knob_status(as_json):
        rows = sorted((p.name, _is_enabled(p)) for p in load_config().packages)
        if as_json:
            import json as _json

            click.echo(_json.dumps(dict(rows), indent=2, sort_keys=True))
            return
        for name, enabled in rows:
            click.echo(f"  [{'on ' if enabled else 'OFF'}] {name}")

    @group.command(
        "enable",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary=f"Enable a package's {kind} (surface it into context).",
            examples=(
                Example(
                    "{prog} " + f"{kind} enable scitex-io",
                    f"Turn {kind} ON for scitex-io.",
                ),
            ),
        ),
    )
    @click.argument("package")
    @click.option(
        "--dry-run", is_flag=True, help="Print what would change; do not write."
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def knob_enable(package, dry_run, yes):
        del yes  # non-interactive; accepted for CLI-audit §2
        if dry_run:
            click.echo(f"would enable {kind} for {package}")
            return
        path = set_package_knob(package, kind, True)
        click.echo(f"{kind} enabled for {package} ({path})")

    @group.command(
        "disable",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary=f"Disable a package's {kind} (stop surfacing it into context).",
            examples=(
                Example(
                    "{prog} " + f"{kind} disable scitex-io",
                    f"Turn {kind} OFF for scitex-io.",
                ),
            ),
        ),
    )
    @click.argument("package")
    @click.option(
        "--dry-run", is_flag=True, help="Print what would change; do not write."
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def knob_disable(package, dry_run, yes):
        del yes  # non-interactive; accepted for CLI-audit §2
        if dry_run:
            click.echo(f"would disable {kind} for {package}")
            return
        path = set_package_knob(package, kind, False)
        click.echo(f"{kind} disabled for {package} ({path})")

    return group


# EOF
