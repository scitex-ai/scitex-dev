#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `list`, `show-graph` (+ deprecated `graph` alias)."""

import json

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def _emit_distributions(package, category, org, as_json, names_only, scan_root=None):
    """Render the origin-remote-identity enumeration (``list --distributions``).

    The output LABELS itself: it names the tree it measured, separates a
    directory count from a distribution count, and states how many
    aliases were collapsed and how many org repos have no local checkout.
    A caller can tell a complete enumeration from a filtered one without
    reading this source.
    """
    from ...._ecosystem import ECOSYSTEM
    from ...._ecosystem._enumerate import (
        enumerate_distributions,
        fetch_org_repos,
        scan_checkout_root,
    )

    if scan_root:
        paths = scan_checkout_root(scan_root)
        filtered = False
        source = f"directory scan of {scan_root}"
    else:
        selected = set(package) if package else set(ECOSYSTEM)
        if category:
            cat_set = set(category)
            selected = {
                p for p in selected if ECOSYSTEM.get(p, {}).get("category") in cat_set
            }
        filtered = bool(package or category)

        from pathlib import Path as _Path

        paths = [
            str(_Path(ECOSYSTEM[p]["local_path"]).expanduser())
            for p in sorted(selected)
            if ECOSYSTEM.get(p, {}).get("local_path")
        ]
        source = "registry local_path entries"

    org_repos = None
    org_error = None
    if org:
        org_repos, org_error = fetch_org_repos(org)
        if org_error:
            org_repos = None

    result = enumerate_distributions(
        paths=paths, org_repos=org_repos, org=org, org_error=org_error
    )

    if names_only:
        for dist in result.distributions:
            click.echo(dist.registry_name or dist.repo)
        return

    if as_json:
        payload = result.to_dict()
        payload["selection"] = "filtered" if filtered else "complete"
        payload["source"] = source
        click.echo(json.dumps(payload))
        return

    scope = "filtered subset" if filtered else "complete"
    click.echo(f"Source: {source} ({scope}).")
    click.echo(result.summary_line())
    if not org:
        click.echo(
            "Org listing NOT queried (pass --org scitex-ai): repos with no "
            "local checkout are NOT represented in these counts."
        )
    click.echo("")
    for dist in result.distributions:
        if not dist.checked_out:
            click.echo(f"  {dist.repo:45s} NOT-CHECKED-OUT")
            continue
        label = dist.registry_name or dist.repo
        click.echo(f"  {label:25s} {dist.repo}")
        for alias in dist.aliases:
            click.echo(f"      alias ({alias.reason}): {alias.path}")
    if result.errors:
        click.echo("")
        click.echo(f"UNREADABLE ({len(result.errors)}) — excluded from counts above:")
        for err in result.errors:
            click.echo(f"  ! {err}", err=True)


def register(ecosystem):
    @ecosystem.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List packages in the SciTeX ecosystem.",
            examples=(
                Example("{prog} ecosystem list", "Table of name + repo."),
                Example("{prog} ecosystem list --json", "Structured JSON output."),
                Example("{prog} ecosystem list -q", "Names only, pipe-friendly."),
                Example(
                    "{prog} ecosystem list -p scitex-io --versions",
                    "One package with version details.",
                ),
                Example("{prog} ecosystem list -c library", "Filter by category."),
                Example(
                    "{prog} ecosystem list --distributions",
                    "Count DISTRIBUTIONS (origin-remote identity), not directories.",
                ),
                Example(
                    "{prog} ecosystem list --distributions --org scitex-ai",
                    "Also surface org repos that have no local checkout.",
                ),
            ),
        ),
    )
    @click.option("--package", "-p", multiple=True, help="Specific packages to check.")
    @click.option(
        "--category",
        "-c",
        multiple=True,
        help=(
            "Filter by package category (library, umbrella, dataset, "
            "external-lib, template). Repeatable. Intersected with -p."
        ),
    )
    @click.option("--versions", is_flag=True, help="Include version details.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.option(
        "--names-only",
        "-q",
        is_flag=True,
        help=(
            "Print only the package names, one per line. Pipe-friendly: "
            "`scitex-dev ecosystem list -q | xargs scitex-dev ecosystem audit-all`."
        ),
    )
    @click.option(
        "--distributions",
        "as_distributions",
        is_flag=True,
        help=(
            "Enumerate DISTRIBUTIONS instead of registry directories: identity "
            "comes from each checkout's origin remote, so duplicate checkouts "
            "and git worktrees collapse into one entry (reported as aliases, "
            "never dropped). Opt-in — the default output shape is unchanged."
        ),
    )
    @click.option(
        "--org",
        default=None,
        help=(
            "With --distributions: cross-reference this GitHub org (e.g. "
            "scitex-ai) so repos with no local checkout are reported as "
            "not-checked-out instead of vanishing."
        ),
    )
    @click.option(
        "--scan-root",
        default=None,
        help=(
            "With --distributions: enumerate every git checkout directly "
            "under this directory (e.g. ~/proj) instead of the registry's "
            "local_path entries. This is the input shape brand-wide sweeps "
            "use, and where duplicate checkouts actually appear."
        ),
    )
    def ecosystem_list(
        package,
        category,
        versions,
        as_json,
        names_only,
        as_distributions,
        org,
        scan_root,
    ):
        from ...._ecosystem import ECOSYSTEM, get_all_packages

        if as_distributions:
            _emit_distributions(
                package, category, org, as_json, names_only, scan_root=scan_root
            )
            return

        pkgs = list(package) if package else get_all_packages()
        if category:
            cat_set = set(category)
            pkgs = [p for p in pkgs if ECOSYSTEM.get(p, {}).get("category") in cat_set]

        if names_only:
            for pkg in pkgs:
                click.echo(pkg)
            return

        if versions:
            from .... import list_versions
            from ..._utils import wrap_as_cli

            wrap_as_cli(list_versions, as_json=as_json, packages=pkgs)
        elif as_json:
            items = [
                {
                    "name": pkg,
                    "github_repo": ECOSYSTEM.get(pkg, {}).get("github_repo", ""),
                }
                for pkg in pkgs
            ]
            click.echo(json.dumps({"packages": items}))
        else:
            for pkg in pkgs:
                info = ECOSYSTEM.get(pkg, {})
                repo = info.get("github_repo", "")
                click.echo(f"  {pkg:25s} {repo}")

    @ecosystem.command(
        "show-graph",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Emit a current-state ecosystem dependency graph (mermaid/DOT).",
            examples=(
                Example("{prog} ecosystem show-graph", "Mermaid graph to stdout."),
                Example(
                    "{prog} ecosystem show-graph --format dot -o /tmp/eco.dot",
                    "DOT graph to a file.",
                ),
                Example("{prog} ecosystem show-graph --cycles", "Detect dependency cycles."),
                Example("{prog} ecosystem show-graph --json", "Nodes/edges as JSON."),
            ),
        ),
    )
    @click.option(
        "--format",
        "fmt",
        type=click.Choice(["mermaid", "dot"]),
        default="mermaid",
        help="Output format.",
    )
    @click.option(
        "--output",
        "-o",
        type=click.Path(dir_okay=False, writable=True),
        default=None,
        help="Write graph to FILE instead of stdout.",
    )
    @click.option(
        "--cycles",
        is_flag=True,
        help="Detect dependency cycles; exit 1 if any are found.",
    )
    @click.option(
        "--include-extras/--no-extras",
        default=True,
        help="Include optional-dependencies in the graph (default: include).",
    )
    @click.option(
        "--group-by-tier/--no-group-by-tier",
        default=True,
        help="Group nodes into tier subgraphs (mermaid only).",
    )
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit graph as JSON edges/nodes."
    )
    @click.pass_context
    def ecosystem_graph(
        ctx, fmt, output, cycles, include_extras, group_by_tier, as_json
    ):
        from ...._ecosystem import _graph as _eg

        pkgs = _eg.discover_packages()
        graph = _eg.build_graph(pkgs)

        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "nodes": list(graph.keys()),
                        "edges": [
                            {"from": src, "to": dst}
                            for src, deps in graph.items()
                            for dst in deps
                        ],
                        "package_count": len(graph),
                    }
                )
            )
            return

        if cycles:
            found = _eg.find_cycles(graph, include_extras=False)
            if not found:
                click.echo("No dependency cycles detected.")
                ctx.exit(0)
            click.echo(f"Detected {len(found)} cycle(s):", err=True)
            for cyc in found:
                click.echo("  - " + " -> ".join(cyc), err=True)
            ctx.exit(1)

        if fmt == "mermaid":
            text = _eg.to_mermaid(
                graph,
                group_by_tier=group_by_tier,
                include_extras=include_extras,
            )
        else:
            text = _eg.to_dot(graph, include_extras=include_extras)

        if output:
            from pathlib import Path as _P

            _P(output).write_text(text, encoding="utf-8")
            click.echo(f"Wrote {len(graph)}-node graph to {output}", err=True)
        else:
            click.echo(text, nl=False)

    # Deprecated bare-noun alias (§1: leaves must be verbs). Removed in 0.11.0.
    @ecosystem.command(
        "graph",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def _ecosystem_graph_deprecated(ctx):
        """(deprecated) Use `ecosystem show-graph`. Removed in 0.11.0."""
        click.echo(
            "warning: `ecosystem graph` was renamed to `ecosystem show-graph` "
            "(verb-noun per §1).",
            err=True,
        )
        target = ecosystem.get_command(ctx, "show-graph")
        if target is None:
            ctx.exit(2)
        ctx.invoke(target, *ctx.args)
