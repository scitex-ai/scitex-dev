"""Thin JSON snapshot adapter over the context accounting API."""

import json

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def register_context_commands(main_group):
    """Register read-only context measurement for standalone/umbrella CLI."""

    @main_group.group(
        "context",
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Measure caller-selected MCP and skill-header metadata.",
            description=(
                "Vendor-neutral JSON bytes and Unicode code points; tokens and "
                "the client's total conversation context are not observed.",
            ),
            examples=(
                Example(
                    "{prog} context measure --input snapshot.json",
                    "Measure a selected metadata snapshot.",
                ),
            ),
        ),
    )
    def context_group():
        pass

    @context_group.command(
        "measure",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Measure a supplied metadata JSON snapshot and emit JSON.",
            description=(
                "Input keys: tools, skill_headers, instructions, tool_owners, "
                "skill_owners. Supply actual advertised tools and selected headers; "
                "this command neither crawls installed providers "
                "nor reads conversations.",
            ),
            examples=(
                Example(
                    "{prog} context measure --input snapshot.json --json",
                    "Read a file and write the report to stdout.",
                ),
                Example(
                    "cat snapshot.json | {prog} context measure --json",
                    "Read JSON from stdin.",
                ),
            ),
        ),
    )
    @click.option(
        "--input",
        "snapshot",
        type=click.File("r", encoding="utf-8"),
        default="-",
        show_default=True,
        help="Metadata snapshot JSON file, or - for stdin.",
    )
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit JSON (also the default output)."
    )
    def measure(snapshot, as_json):
        from ..context import measure_context

        try:
            payload = json.load(snapshot)
            if not isinstance(payload, dict):
                raise ValueError("snapshot must be a JSON object")
            report = measure_context(**payload)
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(json.dumps(report, ensure_ascii=False, sort_keys=True))

    return context_group
