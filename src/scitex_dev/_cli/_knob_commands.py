#!/usr/bin/env python3
"""Shared `status` / `enable` / `disable` knob subcommands.

Attached to the `skills`, `mcp` and `cli` command groups so scitex-dev can
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

    ``kind`` is ``"skills"``, ``"mcp"`` or ``"cli"``.
    """
    from .._core.config import set_package_knob
    from ..exposure import load_exposure_policy

    if kind not in {"skills", "mcp", "cli"}:
        raise ValueError("unsupported exposure surface")

    @group.command(
        "status",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary=f"Show configured owners' {kind} preferences (not provider availability).",
            examples=(
                Example("{prog} " + f"{kind} status", f"Per-package {kind} on/off."),
                Example("{prog} " + f"{kind} status --json", "Structured JSON."),
            ),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    @click.option(
        "--paths",
        "show_paths",
        is_flag=True,
        help="Include selected config/state file locations.",
    )
    def knob_status(as_json, show_paths):
        try:
            policy = load_exposure_policy()
            rows = [(p.distribution, p.is_enabled(kind)) for p in policy.preferences]
        except (TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        if as_json:
            import json as _json

            result = dict(rows)
            if show_paths:
                result = {
                    "config_path": str(policy.config_path),
                    "knob_state_path": str(policy.knob_state_path),
                    "preferences": result,
                }
            click.echo(_json.dumps(result, indent=2, sort_keys=True))
            return
        if show_paths:
            click.echo(f"Config: {policy.config_path}\nState: {policy.knob_state_path}")
        for name, enabled in rows:
            click.echo(f"  [{'on ' if enabled else 'OFF'}] {name}")

    @group.command(
        "enable",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary=f"Enable a package's {kind} aggregation preference.",
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
        try:
            path = set_package_knob(package, kind, True)
        except (TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"{kind} enabled for {package} ({path})")

    @group.command(
        "disable",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary=f"Disable a package's {kind} aggregation preference.",
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
        try:
            path = set_package_knob(package, kind, False)
        except (TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"{kind} disabled for {package} ({path})")

    return group


# EOF
