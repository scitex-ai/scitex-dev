"""``scitex-dev linter list-rules`` / ``list-rules-all`` commands.

Extracted from ``cli.py`` (512-line budget). ``_do_list_rules`` is
re-exported from ``cli`` for back-compat with callers/tests that import
it from there.
"""

from __future__ import annotations

import json
import sys

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ..rules import ALL_RULES


def _do_list_rules(rules_list, as_json):
    if as_json:
        data = [
            {
                "id": r.id,
                "severity": r.severity,
                "category": r.category,
                "message": r.message,
                "suggestion": r.suggestion,
            }
            for r in rules_list
        ]
        click.echo(json.dumps(data, indent=2))
        return
    use_color = sys.stdout.isatty()
    sev_color = {"error": "\033[91m", "warning": "\033[93m", "info": "\033[94m"}
    reset = "\033[0m"
    for r in rules_list:
        if use_color:
            c = sev_color.get(r.severity, "")
            click.echo(f"  {c}{r.id}{reset}  [{r.severity}]  {r.message}")
        else:
            click.echo(f"  {r.id}  [{r.severity}]  {r.message}")
    click.echo(f"\n  {len(rules_list)} rules")


def register(main_group):
    """Attach ``list-rules`` + ``list-rules-all`` to ``main_group``."""

    @main_group.command(
        "list-rules",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List all built-in SciTeX lint rules.",
            examples=(
                Example("{prog} linter list-rules", "Show every built-in rule."),
                Example("{prog} linter list-rules --json", "Machine-readable output."),
                Example(
                    "{prog} linter list-rules --category structure --severity error",
                    "Narrow by category and severity.",
                ),
            ),
        ),
    )
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    @click.option(
        "--category",
        default=None,
        help="Filter by category (comma-separated: structure,import,io,plot,stats).",
    )
    @click.option(
        "--severity",
        type=click.Choice(["error", "warning", "info"]),
        default=None,
        help="Filter by severity.",
    )
    def list_rules_cmd(as_json, category, severity):
        categories = set(category.split(",")) if category else None
        rules_list = list(ALL_RULES.values())
        if categories:
            rules_list = [r for r in rules_list if r.category in categories]
        if severity:
            rules_list = [r for r in rules_list if r.severity == severity]
        _do_list_rules(rules_list, as_json)

    @main_group.command(
        "list-rules-all",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List all SciTeX lint rules, including plugin-contributed ones.",
            examples=(
                Example(
                    "{prog} linter list-rules-all", "Built-in plus plugin rules."
                ),
                Example(
                    "{prog} linter list-rules-all --category io",
                    "Only the io-category rules.",
                ),
            ),
        ),
    )
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    @click.option(
        "--category",
        default=None,
        help="Filter by category (e.g. io, plot, structure).",
    )
    @click.option(
        "--severity",
        type=click.Choice(["error", "warning", "info"]),
        default=None,
        help="Filter by severity.",
    )
    def list_rules_all(as_json, category, severity):
        from .. import list_rules as _lr

        rules_list = _lr(category=category)
        if severity:
            rules_list = [r for r in rules_list if r.severity == severity]
        _do_list_rules(rules_list, as_json)

    return list_rules_cmd, list_rules_all


# EOF
