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
        ("Ecosystem", ["doctor", "ecosystem", "stats"]),
        ("Development", ["config", "rename"]),
        ("Documentation", ["docs", "search", "skills"]),
        ("Integration", ["mcp", "list-python-apis"]),
        ("Shell", ["completion"]),
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

    def _command_to_dict(
        cmd: click.Command,
        parent_ctx: click.Context | None,
        info_name: str,
    ) -> dict:
        """Serialize one click command (and its subcommands recursively) to a dict."""
        sub_ctx = click.Context(cmd, parent=parent_ctx, info_name=info_name)
        options: list[dict] = []
        arguments: list[dict] = []
        for p in cmd.params:
            if isinstance(p, click.Argument):
                arguments.append({"name": p.name, "required": p.required})
            else:
                options.append(
                    {
                        "name": p.name,
                        "opts": list(p.opts),
                        "help": getattr(p, "help", "") or "",
                        "is_flag": bool(getattr(p, "is_flag", False)),
                    }
                )
        out: dict = {
            "name": info_name,
            "help": (cmd.help or "").strip(),
            "short_help": (cmd.short_help or "").strip(),
            "options": options,
            "arguments": arguments,
        }
        if isinstance(cmd, click.Group):
            commands: dict = {}
            for sub in sorted(cmd.list_commands(sub_ctx)):
                sub_cmd = cmd.get_command(sub_ctx, sub)
                if sub_cmd is None:
                    continue
                commands[sub] = _command_to_dict(sub_cmd, sub_ctx, sub)
            out["commands"] = commands
        return out

    def _show_recursive_help(ctx: click.Context) -> None:
        """Recursively show help for all commands. Honours ctx.obj['json']."""
        if ctx.obj and ctx.obj.get("json"):
            import json as _json

            tree = _command_to_dict(
                ctx.command, ctx.parent, ctx.info_name or "scitex-dev"
            )
            click.echo(_json.dumps(tree, indent=2))
            return

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
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Emit structured JSON output (propagates to subcommands that honour it).",
    )
    @click.pass_context
    def main(
        ctx: click.Context,
        version: bool,
        help_recursive: bool,
        as_json: bool,
    ) -> None:
        """scitex-dev - Shared developer utilities for the SciTeX ecosystem."""
        # Expose the root-level --json flag to subcommands via ctx.obj so
        # commands that already honour `--json` can read the inherited
        # setting and default to structured output without the user
        # repeating the flag at each level.
        ctx.ensure_object(dict)
        ctx.obj["json"] = as_json

        if version:
            if as_json:
                import json as _json

                click.echo(
                    _json.dumps(
                        {
                            "name": "scitex-dev",
                            "version": _get_version(),
                        }
                    )
                )
            else:
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

    from ._cli_doctor import register_doctor_command

    register_doctor_command(main)

    from ._cli_ecosystem import register_ecosystem_commands

    register_ecosystem_commands(main)

    from ._cli_stats import register_stats_command

    register_stats_command(main)

    # Quality audits (ecosystem-wide doc/test/line-limit scanners)
    from . import _cli_quality

    @main.group("quality")
    def quality():
        """Ecosystem quality audits (docs, test scope, line limits)."""

    @quality.command("audit-docs")
    @click.option("--projects-root", default=None)
    def _quality_audit_docs(projects_root):
        """Scan SKILL.md / docstring examples for drift."""
        raise SystemExit(_cli_quality.audit_docs(projects_root=projects_root))

    @quality.command("audit-scope")
    @click.option("--projects-root", default=None)
    def _quality_audit_scope(projects_root):
        """Check tests cover the public API surface."""
        raise SystemExit(_cli_quality.audit_scope(projects_root=projects_root))

    @quality.command("audit-lines")
    def _quality_audit_lines():
        """Enforce per-file line limits against the allowlist."""
        raise SystemExit(_cli_quality.audit_lines())

    @quality.command(
        "audit-cli",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def _quality_audit_cli_deprecated(ctx):
        """Deprecated — moved to `scitex-dev ecosystem audit-cli` (§5)."""
        click.echo(
            "error: `scitex-dev quality audit-cli` was renamed to "
            "`scitex-dev ecosystem audit-cli`.",
            err=True,
        )
        click.echo(
            "Re-run with: scitex-dev ecosystem audit-cli " + " ".join(ctx.args),
            err=True,
        )
        raise SystemExit(2)

    @quality.command("audit-frontmatter")
    @click.argument("root", type=click.Path(exists=True, file_okay=False))
    def _quality_audit_frontmatter(root):
        """Check skill YAML frontmatter (description length, canonical-location, context_tokens drift, group tags). Warn-only."""
        from ._cli_quality_frontmatter import audit_frontmatter

        raise SystemExit(audit_frontmatter(root))

    # -------------------------------------------------------------------
    # Development commands
    # -------------------------------------------------------------------

    @main.command(
        "config", hidden=True, context_settings={"ignore_unknown_options": True}
    )
    @click.pass_context
    def config_deprecated(ctx):
        """(deprecated) Renamed to `show-config`."""
        click.echo(
            "error: `scitex-dev config` was renamed to `scitex-dev show-config`.\n"
            "Re-run with: scitex-dev show-config",
            err=True,
        )
        ctx.exit(2)

    @main.command("show-config")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def config_cmd(as_json):
        """Show dev configuration."""
        from . import config_to_dict, load_config

        cfg = config_to_dict(load_config())

        if as_json:
            click.echo(json.dumps(cfg, indent=2, default=str))
            return

        # Human-readable text output: section headers + tabular rows
        sections = [
            ("Packages", "packages", ["name", "github_repo", "local_path"]),
            ("Hosts", "hosts", None),
            ("GitHub Remotes", "github_remotes", None),
            ("Branches", "branches", None),
        ]
        for title, key, cols in sections:
            items = cfg.get(key, [])
            if not items:
                continue
            click.echo(f"\n{title} ({len(items)})")
            click.echo("=" * (len(title) + 4 + len(str(len(items)))))
            for item in items:
                if isinstance(item, dict) and cols:
                    parts = [str(item.get(c, "")) for c in cols]
                    click.echo(
                        "  "
                        + "  ".join(
                            f"{p:25s}" if i == 0 else p for i, p in enumerate(parts)
                        )
                    )
                elif isinstance(item, dict):
                    click.echo("  " + " | ".join(f"{k}={v}" for k, v in item.items()))
                else:
                    click.echo(f"  {item}")

    @main.command(
        "rename",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def rename_deprecated(ctx):
        """(deprecated) Renamed to `rename-symbols`."""
        click.echo(
            "error: `scitex-dev rename` was renamed to `scitex-dev rename-symbols`.\n"
            "Re-run with: scitex-dev rename-symbols <old> <new> [...]",
            err=True,
        )
        ctx.exit(2)

    @main.command("rename-symbols")
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
    def rename_symbols(old_name, new_name, root, dry_run, regex, exclude, as_json):
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

    from ._cli_completion import register_completion_command

    register_completion_command(main)

    @main.command(
        "search",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def search_deprecated(ctx):
        """(deprecated) Renamed to `search-docs`."""
        click.echo(
            "error: `scitex-dev search` was renamed to `scitex-dev search-docs`.\n"
            "Re-run with: scitex-dev search-docs <query> [...]",
            err=True,
        )
        ctx.exit(2)

    @main.command("search-docs")
    @click.argument("query")
    @click.option(
        "--scope", default="all", help="Search scope: all, api, cli, mcp, docs."
    )
    @click.option("--max-results", default=10, help="Maximum results.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def search_docs(query, scope, max_results, as_json):
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

    @mcp.command(
        "installation",
        hidden=True,
        context_settings={"ignore_unknown_options": True},
    )
    @click.pass_context
    def mcp_installation_deprecated(ctx):
        """(deprecated) Renamed to `show-installation`."""
        click.echo(
            "error: `scitex-dev mcp installation` was renamed to "
            "`scitex-dev mcp show-installation`.\n"
            "Re-run with: scitex-dev mcp show-installation",
            err=True,
        )
        ctx.exit(2)

    @mcp.command("show-installation")
    def mcp_show_installation():
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
