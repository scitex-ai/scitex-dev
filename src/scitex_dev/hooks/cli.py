#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/hooks/cli.py
"""The ``<pkg> dev hooks list-rules …`` command, mountable by ANY leaf package.

PUBLIC on purpose, like :mod:`scitex_dev.secret.cli`. §13 says every package
mounts its self-maintenance surfaces under one ``dev`` group; this module is
how a leaf gets the guardrail-declaration half of that surface without
reimplementing it::

    from scitex_dev.hooks.cli import register_hook_rules_command

    @main.group("dev")
    def dev() -> None:
        ...

    @dev.group("hooks")
    def hooks() -> None:
        ...

    register_hook_rules_command(hooks, provider="scitex-agent-container")

``provider`` scopes the listing to the mounting package's OWN declarations,
which is what ``<pkg> dev hooks list-rules`` means: this package's upkeep, as a
leaf. The fleet-wide aggregate is a different command --
``scitex-dev ecosystem dev list-hooks`` -- and lives in the ecosystem group.

scitex-dev consumes this registrar exactly as a leaf would rather than
keeping a private copy, so that scitex-dev's copy is not the only one that
ever gets fixed.
"""

from __future__ import annotations

import json as _json

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ._discover import discover_hooks
from ._spec import ALLOWED_EVENTS, HookRule


def rule_to_dict(rule: HookRule) -> dict:
    """Render one rule as a JSON-safe dict. The machine-readable contract."""
    return {
        "id": rule.id,
        "rule": rule.rule,
        "reason": rule.reason,
        "event": rule.event,
        "severity": rule.severity,
        "matches": list(rule.matches),
        "provider": rule.provider,
        "script": rule.script,
        "predicate": rule.predicate,
        "check": rule.check,
        "bypass": rule.bypass,
        "implemented_in": rule.implemented_in,
        "doctrine": rule.doctrine,
    }


def _echo_human(rules: list[HookRule], *, show_provider: bool) -> None:
    """Human rendering. Every rule prints its REASON -- that is the point."""
    if not rules:
        click.echo("No hook rules declared.")
        return
    for rule in rules:
        head = f"  [{rule.severity}] {rule.id}"
        if show_provider:
            head += f"  ({rule.provider})"
        click.echo(head)
        click.echo(f"      rule:   {rule.rule}")
        click.echo(f"      reason: {rule.reason}")
        click.echo(f"      on:     {rule.event}  {', '.join(rule.matches)}")
        if rule.bypass:
            click.echo(f"      bypass: {rule.bypass}")
    providers = sorted({r.provider for r in rules})
    click.echo(
        f"\n{len(rules)} rule(s) across {len(providers)} provider(s): "
        f"{', '.join(providers)}"
    )


def register_hook_rules_command(
    parent: click.Group,
    *,
    provider: str | None = None,
    name: str = "list-rules",
) -> click.Command:
    """Mount the ``list-rules`` leaf on *parent* (a package's ``dev hooks`` group).

    NAMED WITH ITS VERB, not `rules`. §1 rejects a leaf token that is a bare
    noun — `dev hooks rules` reads as though `hooks` were transitive over
    `rules`, and the reader cannot tell whether it lists, edits or applies
    them. The remedy the rule offers is `<verb>-rules`, and listing is what
    this does.

    Caught by the audit gate on this branch rather than in review, which is
    the gate working: the name was wrong from the first commit and no human
    reading it noticed.

    ``provider`` scopes the listing to one package's declarations; ``None``
    lists everything discovered, which is what the ecosystem aggregate wants.
    Returns the command so a caller can further customise it.
    """

    @parent.command(
        name,
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List this package's declared agent guardrail rules.",
            description=(
                "Every guardrail this package OWNS, with the rule it "
                "enforces and the reason it exists. Declarations are "
                "federated through the `scitex_dev.hooks` entry-point "
                "group, so this is the same data the ecosystem aggregate "
                "and the auditor read -- not a separate list that can "
                "drift from them."
            ),
            examples=(
                Example("{prog} dev hooks list-rules", "List declared rules."),
                Example(
                    "{prog} dev hooks list-rules --json",
                    "Machine-readable output.",
                ),
                Example(
                    "{prog} dev hooks list-rules --event pre-tool-use",
                    "Only rules attaching to PreToolUse.",
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
        "--severity",
        type=click.Choice(("deny", "warn", "advise")),
        default=None,
        help="Restrict to rules of this severity.",
    )
    def rules_cmd(as_json: bool, event: str | None, severity: str | None) -> None:
        found = discover_hooks(event=event)
        if provider is not None:
            found = [r for r in found if r.provider == provider]
        if severity is not None:
            found = [r for r in found if r.severity == severity]

        if as_json:
            click.echo(_json.dumps([rule_to_dict(r) for r in found], indent=2))
            return
        _echo_human(found, show_provider=provider is None)

    return rules_cmd


__all__ = ["register_hook_rules_command", "rule_to_dict"]
