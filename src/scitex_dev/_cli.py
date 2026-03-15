#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main CLI entry point for scitex-dev."""

import json
import sys

try:
    import click
except ImportError:

    def main(argv=None):
        print(
            "ERROR: click is not installed. Install with: pip install scitex-dev[cli]",
            file=sys.stderr,
        )
        raise SystemExit(1)

else:
    CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

    COMMAND_CATEGORIES = [
        ("Ecosystem", ["ecosystem"]),
        ("Development", ["config", "rename"]),
        ("Documentation", ["docs", "search", "skills"]),
        ("Integration", ["mcp", "list-python-apis"]),
    ]

    class CategorizedGroup(click.Group):
        """Custom Click group that displays commands organized by category."""

        def format_commands(self, ctx, formatter):
            commands = {}
            for subcommand in self.list_commands(ctx):
                cmd = self.get_command(ctx, subcommand)
                if cmd is not None and not cmd.hidden:
                    commands[subcommand] = cmd

            if not commands:
                return

            displayed = set()

            for category_name, category_commands in COMMAND_CATEGORIES:
                category_items = []
                for name in category_commands:
                    if name in commands and name not in displayed:
                        cmd = commands[name]
                        help_text = cmd.get_short_help_str(limit=formatter.width)
                        category_items.append((name, help_text))
                        displayed.add(name)

                if category_items:
                    with formatter.section(category_name):
                        formatter.write_dl(category_items)

            uncategorized = [
                (name, commands[name].get_short_help_str(limit=formatter.width))
                for name in sorted(commands.keys())
                if name not in displayed
            ]
            if uncategorized:
                with formatter.section("Other"):
                    formatter.write_dl(uncategorized)

    def _show_recursive_help(ctx: click.Context) -> None:
        """Recursively show help for all commands."""
        click.echo(ctx.get_help())
        click.echo()
        group = ctx.command
        if isinstance(group, click.Group):
            for name in sorted(group.list_commands(ctx)):
                cmd = group.get_command(ctx, name)
                sub_ctx = click.Context(cmd, parent=ctx, info_name=name)
                click.echo(f"{'=' * 60}")
                click.echo(f"Command: {name}")
                click.echo(f"{'=' * 60}")
                click.echo(sub_ctx.get_help())
                click.echo()
                if isinstance(cmd, click.Group):
                    for sub_name in sorted(cmd.list_commands(sub_ctx)):
                        sub_cmd = cmd.get_command(sub_ctx, sub_name)
                        sub_sub_ctx = click.Context(
                            sub_cmd, parent=sub_ctx, info_name=sub_name
                        )
                        click.echo(f"  {'─' * 56}")
                        click.echo(f"  Subcommand: {name} {sub_name}")
                        click.echo(f"  {'─' * 56}")
                        click.echo(sub_sub_ctx.get_help())
                        click.echo()

    def _get_version() -> str:
        try:
            from importlib.metadata import version

            return version("scitex-dev")
        except Exception:
            return "0.0.0-unknown"

    @click.group(
        cls=CategorizedGroup,
        invoke_without_command=True,
        context_settings=CONTEXT_SETTINGS,
    )
    @click.option("--version", "-V", is_flag=True, help="Show version and exit.")
    @click.option("--help-recursive", is_flag=True, help="Show help for all commands.")
    @click.pass_context
    def main(ctx: click.Context, version: bool, help_recursive: bool) -> None:
        """scitex-dev - Shared developer utilities for the SciTeX ecosystem."""
        if version:
            click.echo(f"scitex-dev {_get_version()}")
            ctx.exit(0)

        if help_recursive:
            _show_recursive_help(ctx)
            ctx.exit(0)

        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    # -------------------------------------------------------------------
    # Ecosystem commands
    # -------------------------------------------------------------------

    @main.group(invoke_without_command=True)
    @click.option(
        "--help-recursive", is_flag=True, help="Show help for all subcommands."
    )
    @click.pass_context
    def ecosystem(ctx, help_recursive):
        """Manage the SciTeX ecosystem (versions, sync, fixes)."""
        if help_recursive:
            _print_ecosystem_help_recursive(ctx)
            ctx.exit(0)
        elif ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    def _print_ecosystem_help_recursive(ctx):
        fake_parent = click.Context(click.Group(), info_name="scitex-dev")
        parent_ctx = click.Context(ecosystem, info_name="ecosystem", parent=fake_parent)

        click.secho("=== scitex-dev ecosystem ===", fg="cyan", bold=True)
        click.echo(ecosystem.get_help(parent_ctx))

        for name in sorted(ecosystem.list_commands(ctx) or []):
            cmd = ecosystem.get_command(ctx, name)
            if cmd is None:
                continue
            click.echo()
            click.secho(f"=== scitex-dev ecosystem {name} ===", fg="cyan", bold=True)
            with click.Context(cmd, info_name=name, parent=parent_ctx) as sub_ctx:
                click.echo(cmd.get_help(sub_ctx))

    @ecosystem.command("list")
    @click.option("--package", "-p", multiple=True, help="Specific packages to check.")
    @click.option("--versions", is_flag=True, help="Include version details.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def ecosystem_list(package, versions, as_json):
        """List packages in the SciTeX ecosystem."""
        from .ecosystem import ECOSYSTEM, get_all_packages

        pkgs = list(package) if package else get_all_packages()

        if versions:
            from . import list_versions
            from .cli_utils import wrap_as_cli

            wrap_as_cli(list_versions, as_json=as_json, packages=pkgs)
        elif as_json:
            click.echo(json.dumps({"packages": pkgs}))
        else:
            for pkg in pkgs:
                info = ECOSYSTEM.get(pkg, {})
                repo = info.get("github_repo", "")
                click.echo(f"  {pkg:25s} {repo}")

    @ecosystem.command("fix-mismatches")
    @click.option("--dry-run", is_flag=True, help="Preview without applying fixes.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def ecosystem_fix_mismatches(dry_run, as_json):
        """Detect and fix version mismatches across ecosystem."""
        from . import fix_mismatches
        from .cli_utils import wrap_as_cli

        wrap_as_cli(fix_mismatches, as_json=as_json, dry_run=dry_run)

    @ecosystem.command("sync")
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--dry-run", is_flag=True, help="Preview without syncing.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def ecosystem_sync(package, dry_run, as_json):
        """Sync ecosystem packages locally (pip install -e)."""
        from .cli_utils import wrap_as_cli
        from .sync import sync_local

        pkgs = list(package) if package else None
        wrap_as_cli(sync_local, as_json=as_json, packages=pkgs, dry_run=dry_run)

    # -------------------------------------------------------------------
    # Development commands
    # -------------------------------------------------------------------

    @main.command("config")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def config_cmd(as_json):
        """Show dev configuration."""
        from . import config_to_dict, load_config
        from .cli_utils import wrap_as_cli

        def _get_config():
            cfg = load_config()
            return config_to_dict(cfg)

        wrap_as_cli(_get_config, as_json=as_json)

    @main.command()
    @click.argument("old_name")
    @click.argument("new_name")
    @click.option("--root", default=".", help="Root directory for rename.")
    @click.option("--dry-run", is_flag=True, help="Preview without renaming.")
    @click.option("--regex", is_flag=True, help="Treat pattern as Python regex.")
    @click.option(
        "--exclude",
        multiple=True,
        help="Exclude paths containing this substring. Repeatable.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def rename(old_name, new_name, root, dry_run, regex, exclude, as_json):
        """Bulk rename with cross-reference updates. Supports --regex for regex patterns."""
        from .cli_utils import wrap_as_cli

        extra_excludes = list(exclude) if exclude else []

        if dry_run:
            from . import preview_rename

            wrap_as_cli(
                preview_rename,
                as_json=as_json,
                pattern=old_name,
                replacement=new_name,
                directory=root,
                regex=regex,
                extra_excludes=extra_excludes,
            )
        else:
            from . import execute_rename

            wrap_as_cli(
                execute_rename,
                as_json=as_json,
                pattern=old_name,
                replacement=new_name,
                directory=root,
                regex=regex,
                extra_excludes=extra_excludes,
            )

    # -------------------------------------------------------------------
    # Documentation commands
    # -------------------------------------------------------------------

    from .cli import docs_click_group

    main.add_command(docs_click_group(package="scitex-dev"))

    from ._cli_skills import register_skills_commands

    register_skills_commands(main)

    @main.command()
    @click.argument("query")
    @click.option(
        "--scope", default="all", help="Search scope: all, api, cli, mcp, docs."
    )
    @click.option("--max-results", default=10, help="Maximum results.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def search(query, scope, max_results, as_json):
        """Search across APIs, CLI, MCP tools, and documentation."""
        from . import search as do_search
        from .cli_utils import wrap_as_cli

        wrap_as_cli(
            do_search,
            as_json=as_json,
            query=query,
            scope=scope,
            max_results=max_results,
        )

    # -------------------------------------------------------------------
    # Integration commands
    # -------------------------------------------------------------------

    @main.group(invoke_without_command=True)
    @click.option(
        "--help-recursive", is_flag=True, help="Show help for all subcommands."
    )
    @click.pass_context
    def mcp(ctx, help_recursive):
        """MCP (Model Context Protocol) server commands."""
        if help_recursive:
            _print_mcp_help_recursive(ctx)
            ctx.exit(0)
        elif ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    def _print_mcp_help_recursive(ctx):
        fake_parent = click.Context(click.Group(), info_name="scitex-dev")
        parent_ctx = click.Context(mcp, info_name="mcp", parent=fake_parent)

        click.secho("=== scitex-dev mcp ===", fg="cyan", bold=True)
        click.echo(mcp.get_help(parent_ctx))

        for name in sorted(mcp.list_commands(ctx) or []):
            cmd = mcp.get_command(ctx, name)
            if cmd is None:
                continue
            click.echo()
            click.secho(f"=== scitex-dev mcp {name} ===", fg="cyan", bold=True)
            with click.Context(cmd, info_name=name, parent=parent_ctx) as sub_ctx:
                click.echo(cmd.get_help(sub_ctx))

    @mcp.command("start")
    def mcp_start():
        """Start the scitex-dev MCP server."""
        try:
            from ._mcp_server import mcp as mcp_server
        except ImportError as e:
            raise click.ClickException(
                f"Failed to import MCP server. "
                f"Install fastmcp: pip install scitex-dev[mcp]\n{e}"
            ) from e

        click.echo("Starting scitex-dev MCP server...")
        mcp_server.run()

    @mcp.command("doctor")
    def mcp_doctor():
        """Check MCP server dependencies and configuration."""
        click.echo("Checking MCP dependencies...")

        try:
            import fastmcp

            click.echo(f"  [OK] fastmcp {fastmcp.__version__}")
        except ImportError:
            click.echo("  [!!] fastmcp not installed")
            click.echo("    Install with: pip install scitex-dev[mcp]")
            return

        try:
            from ._mcp_server import mcp as mcp_server

            import asyncio

            tool_count = len(asyncio.run(mcp_server.list_tools()))
            click.echo(f"  [OK] MCP server loaded ({tool_count} tools)")
        except Exception as e:
            click.echo(f"  [!!] MCP server error: {e}")
            return

        click.echo()
        click.echo("MCP server is ready.")
        click.echo("Run with: scitex-dev mcp start")

    @mcp.command("installation")
    def mcp_installation():
        """Show installation instructions for MCP server integration."""
        click.echo("Install scitex-dev with MCP support:")
        click.echo()
        click.echo("  pip install scitex-dev[mcp]")
        click.echo()
        click.echo("Add to your MCP client configuration:")
        click.echo()
        click.echo("  {")
        click.echo('    "mcpServers": {')
        click.echo('      "scitex-dev": {')
        click.echo('        "command": "scitex-dev",')
        click.echo('        "args": ["mcp", "start"]')
        click.echo("      }")
        click.echo("    }")
        click.echo("  }")
        click.echo()
        click.echo("Verify with:")
        click.echo("  scitex-dev mcp doctor")
        click.echo("  scitex-dev mcp list-tools")

    @mcp.command("list-tools")
    @click.option(
        "-v", "--verbose", count=True, help="Verbosity: -v sig, -vv +desc, -vvv full."
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def mcp_list_tools(verbose, as_json):
        """List available MCP tools."""
        try:
            from ._mcp_server import mcp as mcp_server
        except ImportError as e:
            raise click.ClickException(
                f"fastmcp not installed. Install with: pip install scitex-dev[mcp]\n{e}"
            ) from e

        import asyncio

        tools = asyncio.run(mcp_server.list_tools())
        total = len(tools)

        if as_json:
            from .types import RESULT_SCHEMA

            output = {
                "result_envelope": RESULT_SCHEMA,
                "total": total,
                "tools": [
                    {"name": t.name, "description": t.description or ""} for t in tools
                ],
            }
            click.echo(json.dumps(output, indent=2))
            return

        click.secho(f"scitex-dev MCP: {total} tools", fg="cyan", bold=True)
        click.echo(
            "Returns: Result{success, data, error, error_code, context, hints_on_error}"
        )
        click.echo()

        for tool in sorted(tools, key=lambda t: t.name):
            if verbose == 0:
                click.echo(f"  {tool.name}")
            else:
                click.echo(f"  {tool.name}")
                if tool.description:
                    desc = tool.description.split("\n")[0].strip()
                    click.echo(f"    {desc}")
                click.echo(f"    -> Result")
                click.echo()

    # -------------------------------------------------------------------
    # list-python-apis
    # -------------------------------------------------------------------

    @main.command("list-python-apis")
    @click.option(
        "-v", "--verbose", count=True, help="Verbosity: -v sig+doc1, -vv full doc."
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def list_python_apis(verbose, as_json):
        """List Python APIs (scitex-dev public API tree)."""
        import inspect

        import scitex_dev

        items = []
        for name in sorted(scitex_dev.__all__):
            obj = getattr(scitex_dev, name, None)
            if obj is None:
                continue
            if inspect.isclass(obj):
                kind = "C"
            elif callable(obj):
                kind = "F"
            else:
                kind = "V"
            doc = inspect.getdoc(obj) or ""
            items.append({"name": name, "type": kind, "doc": doc})

        if as_json:
            click.echo(json.dumps(items, indent=2))
            return

        click.secho(
            f"scitex-dev public API ({len(items)} items):", fg="cyan", bold=True
        )
        for item in items:
            t = item["type"]
            click.echo(f"  [{t}] {item['name']}")
            if verbose >= 1 and item["doc"]:
                desc = item["doc"].split("\n")[0][:70]
                click.echo(f"      {desc}")
