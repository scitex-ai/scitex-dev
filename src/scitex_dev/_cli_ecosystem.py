#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI commands for ecosystem management -- registered on main CLI group."""

import json

import click


def register_ecosystem_commands(main_group):
    """Register ecosystem command group on the main CLI."""

    @main_group.group(invoke_without_command=True)
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

        wrap_as_cli(fix_mismatches, as_json=as_json, confirm=not dry_run)

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

    @ecosystem.command("dashboard")
    @click.option("--port", default=8050, type=int, help="Port to serve on.")
    @click.option("--host", default="127.0.0.1", help="Host to bind to.")
    @click.option("--debug", is_flag=True, help="Enable debug/reload mode.")
    @click.option(
        "--no-browser", is_flag=True, help="Do not open browser automatically."
    )
    @click.option("--force", is_flag=True, help="Kill existing process on the port.")
    @click.option(
        "--background", is_flag=True, help="Run dashboard in a background process."
    )
    def ecosystem_dashboard(port, host, debug, no_browser, force, background):
        """Launch the ecosystem dashboard web UI."""
        if background:
            import subprocess
            import sys

            code = (
                "from scitex_dev.dashboard import run_dashboard; "
                f"run_dashboard(port={port}, host={host!r}, debug={debug}, "
                f"open_browser={not no_browser}, force={force})"
            )
            subprocess.Popen(
                [sys.executable, "-c", code],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            click.echo(f"Dashboard started in background on {host}:{port}")
        else:
            from .dashboard import run_dashboard

            run_dashboard(
                port=port,
                host=host,
                debug=debug,
                open_browser=not no_browser,
                force=force,
            )
