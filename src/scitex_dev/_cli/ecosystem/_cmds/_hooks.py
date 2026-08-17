#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/ecosystem/_cmds/_hooks.py
"""``scitex-dev ecosystem dev hooks`` — the federated agent-guardrail corpus.

The fleet-wide half of §13's hook surface. ``<pkg> dev hooks rules`` shows one
package's declarations; this shows every installed package's, aggregated
through the ``scitex_dev.hooks`` entry-point group.

scitex-dev appears here as one PROVIDER ROW among the others. It is not
special-cased into the listing and holds no privileged position: its rules
arrive through the same entry point every leaf uses.
"""

from __future__ import annotations

import json as _json

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ....hooks import ALLOWED_EVENTS, discover_hooks
from ....hooks.cli import rule_to_dict


def register(parent: click.Group) -> click.Command:
    """Mount ``hooks`` on the ``ecosystem dev`` group."""

    @parent.command(
        # `list-hooks`, not `hooks`: §1 rejects a bare-noun leaf token, because
        # `ecosystem dev hooks` gives the reader no way to tell listing from
        # installing or running them. The rule's own remedy is `<verb>-hooks`.
        "list-hooks",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Every package's declared agent guardrail rules.",
            description=(
                "Aggregates the `scitex_dev.hooks` entry points each package "
                "publishes, so one command shows the whole fleet's guardrail "
                "policy -- each rule with the reason it exists -- rather than "
                "one package's. Distinct from `scitex-dev dev hooks list-rules`, "
                "which is scitex-dev's OWN declarations as a leaf."
            ),
            examples=(
                Example(
                    "{prog} ecosystem dev list-hooks",
                    "List every package's declared rules.",
                ),
                Example(
                    "{prog} ecosystem dev list-hooks --json",
                    "Machine-readable output.",
                ),
                Example(
                    "{prog} ecosystem dev list-hooks --provider scitex-agent-container",
                    "Only one package's rules.",
                ),
            ),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    @click.option(
        "--event",
        type=click.Choice(ALLOWED_EVENTS),
        default=None,
        help="Restrict to rules attaching to this lifecycle point.",
    )
    @click.option(
        "--provider",
        default=None,
        help="Restrict to rules declared by this package.",
    )
    def hooks_cmd(as_json: bool, event: str | None, provider: str | None) -> None:
        rules = discover_hooks(event=event)
        if provider is not None:
            rules = [r for r in rules if r.provider == provider]

        if as_json:
            click.echo(_json.dumps([rule_to_dict(r) for r in rules], indent=2))
            return

        if not rules:
            click.echo("No hook rules declared by any installed package.")
            return

        try:
            from rich.console import Console
            from rich.table import Table
        except ImportError:  # pragma: no cover - rich is a hard dep in practice
            for rule in rules:
                click.echo(f"  {rule.id:44s} {rule.severity:7s} {rule.provider}")
        else:
            table = Table(show_header=True, header_style="bold")
            table.add_column("rule id", overflow="fold")
            table.add_column("sev")
            table.add_column("event")
            table.add_column("what it enforces", overflow="fold")
            table.add_column("provider", overflow="fold")
            for rule in rules:
                table.add_row(
                    rule.id,
                    rule.severity,
                    rule.event,
                    rule.rule,
                    rule.provider,
                )
            Console().print(table)

        providers = sorted({r.provider for r in rules})
        click.echo(
            f"{len(rules)} rule(s) across {len(providers)} provider(s): "
            f"{', '.join(providers)}"
        )

    return hooks_cmd


__all__ = ["register"]
