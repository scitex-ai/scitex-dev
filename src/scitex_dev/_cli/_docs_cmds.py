"""Documentation dispatcher commands and inert installed-provider discovery."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import click

from .._core.dispatch import docs_click_group
from .._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register_docs_commands(main):
    """Attach the shared package docs commands plus Dev's provider catalog."""
    docs_grp = docs_click_group(package="scitex-dev")
    main.add_command(docs_grp)

    @docs_grp.command(
        "validate",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Check Markdown Python references and call arguments without execution.",
            description=(
                "Defaults to README.md and src/*/_skills/**/*.md. --document "
                "selects explicit files relative to --path. Local references and "
                "plain function argument bindings are checked in top-level Python "
                "fences. Argument types and values, prose, runtime results and other "
                "interfaces are not validated. Exit 0 "
                "means ok within checked_scope; 1 means needs_update; 2 means "
                "incomplete. Inspect unverified and limitations, even with exit 0."
            ),
            examples=(
                Example(
                    "{prog} docs validate --path . --json",
                    "Static local-source report.",
                ),
                Example(
                    "{prog} docs validate --path . --document AGENTS.md --json",
                    "Select an existing agent document.",
                ),
            ),
        ),
    )
    @click.option(
        "--path",
        "package_path",
        default=".",
        type=click.Path(exists=True, file_okay=False, path_type=Path),
        help="Local source package root (default: current directory).",
    )
    @click.option(
        "--document",
        "documents",
        multiple=True,
        type=click.Path(path_type=Path),
        help="Explicit Markdown file relative to --path; repeat to select more.",
    )
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit the full scoped report."
    )
    @click.pass_context
    def docs_validate(ctx, package_path, documents, as_json):
        from .. import verify_docs_and_skills

        report = verify_docs_and_skills(
            package_path, documents=documents if documents else None
        )
        if as_json:
            click.echo(json.dumps(report, indent=2))
        else:
            click.echo(f"Static Markdown/source check: {report['status']}")
            click.echo(
                f"Documents checked: {len(report['checked_scope']['documents'])}"
            )
            for key in ("issues", "unverified", "limitations"):
                for item in report[key]:
                    click.echo(f"{key}: {item}")
        ctx.exit({"ok": 0, "needs_update": 1, "incomplete": 2}.get(report["status"], 2))

    # `docs search` — canonical home for ecosystem-wide search across APIs,
    # CLI, MCP tools, and documentation. The legacy top-level `search-docs`
    # is kept as a hidden deprecation alias (see below). Removed in 0.11.0.
    @docs_grp.command(
        "search",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Search across APIs, CLI, MCP tools, and documentation.",
            examples=(
                Example(
                    '{prog} docs search "save figure"', "Full-text search everywhere."
                ),
                Example(
                    "{prog} docs search version --scope api", "Limit to the API scope."
                ),
                Example(
                    "{prog} docs search hpc --max-results 20 --json",
                    "More hits, as JSON.",
                ),
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
        "list-providers",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List leaf-owned installed documentation declarations without loading them.",
            examples=(
                Example(
                    "{prog} docs list-providers --json",
                    "Metadata-only provider catalog.",
                ),
            ),
        ),
    )
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit normalized provider metadata."
    )
    def docs_providers(as_json):
        from ..doc_providers import list_doc_providers

        rows = list_doc_providers()
        names = Counter(row.name for row in rows)
        result = {
            "schema_version": "scitex-doc-providers/1",
            "providers": [asdict(row) for row in rows],
            "ambiguous_names": sorted(
                name for name, count in names.items() if count > 1
            ),
            "declarations_only": True,
            "live_verified": False,
        }
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            for row in rows:
                duplicate = " [ambiguous name]" if names[row.name] > 1 else ""
                click.echo(
                    f"{row.name}: {row.distribution} {row.version or 'unknown'}{duplicate}"
                )
            click.echo(
                "Installed declarations only; provider execution and live availability unverified."
            )

    return docs_grp


__all__ = ["register_docs_commands"]
