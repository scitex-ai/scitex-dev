"""Documentation dispatcher commands and inert installed-provider discovery."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json

import click

from .._core.dispatch import docs_click_group
from .._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register_docs_commands(main):
    """Attach the shared package docs commands plus Dev's provider catalog."""
    docs_grp = docs_click_group(package="scitex-dev")
    main.add_command(docs_grp)

    # `docs search` — canonical home for ecosystem-wide search across APIs,
    # CLI, MCP tools, and documentation. The legacy top-level `search-docs`
    # is kept as a hidden deprecation alias (see below). Removed in 0.11.0.
    @docs_grp.command(
        "search",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Search across APIs, CLI, MCP tools, and documentation.",
            examples=(
                Example('{prog} docs search "save figure"', "Full-text search everywhere."),
                Example("{prog} docs search version --scope api", "Limit to the API scope."),
                Example("{prog} docs search hpc --max-results 20 --json", "More hits, as JSON."),
            ),
        ),
    )
    @click.argument("query")
    @click.option(
        "--scope", default="all", help="Search scope: all, api, cli, mcp, docs."
    )
    @click.option("--max-results", default=10, help="Maximum results.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def _docs_search(query, scope, max_results, as_json):
        from .. import search as do_search
        from ._utils import wrap_as_cli

        wrap_as_cli(
            do_search,
            as_json=as_json,
            query=query,
            scope=scope,
            max_results=max_results,
        )

    @docs_grp.command(
        "providers", cls=SpecCommand,
        help_spec=CliHelp(
            summary="List leaf-owned installed documentation declarations without loading them.",
            examples=(Example("{prog} docs providers --json", "Metadata-only provider catalog."),),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit normalized provider metadata.")
    def docs_providers(as_json):
        from ..doc_providers import list_doc_providers

        rows = list_doc_providers()
        names = Counter(row.name for row in rows)
        result = {
            "schema_version": "scitex-doc-providers/1",
            "providers": [asdict(row) for row in rows],
            "ambiguous_names": sorted(name for name, count in names.items() if count > 1),
            "declarations_only": True,
            "live_verified": False,
        }
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            for row in rows:
                duplicate = " [ambiguous name]" if names[row.name] > 1 else ""
                click.echo(f"{row.name}: {row.distribution} {row.version or 'unknown'}{duplicate}")
            click.echo("Installed declarations only; provider execution and live availability unverified.")

    return docs_grp


__all__ = ["register_docs_commands"]
