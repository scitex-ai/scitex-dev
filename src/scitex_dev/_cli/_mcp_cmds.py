"""MCP (Model Context Protocol) subcommands for `scitex-dev`.

Extracted from `_root.py` to keep the orchestrator under the 512-line
budget. All commands attach to the root `main` group via
`register_mcp_commands(main)`.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def register_mcp_commands(main: click.Group) -> click.Group:
    """Attach the `mcp` group + its subcommands to *main*."""

    @main.group(
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="MCP (Model Context Protocol) server commands.",
            examples=(
                Example("{prog} mcp start", "Start the MCP server."),
                Example("{prog} mcp doctor", "Check MCP dependencies."),
                Example("{prog} mcp list-tools", "List available MCP tools."),
            ),
        ),
    )
    @click.option(
        "--help-recursive", is_flag=True, help="Show help for all subcommands."
    )
    @click.pass_context
    def mcp(ctx, help_recursive):
        if help_recursive:
            _print_mcp_help_recursive(ctx, mcp)
            ctx.exit(0)
        elif ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @mcp.command(
        "start",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Start the scitex-dev MCP server.",
            description=(
                "Runs the fastmcp server on stdio, blocking until killed. "
                "FastMCP is a base dependency.",
            ),
            examples=(
                Example("{prog} mcp start", "Start the server on stdio."),
                Example("{prog} mcp start --dry-run", "Preview without starting."),
            ),
        ),
    )
    @click.option(
        "--dry-run", is_flag=True, help="Print what would be done; do not start."
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def mcp_start(dry_run, yes):
        del yes  # accepted for §2; mcp start is non-interactive
        if dry_run:
            click.echo("would start scitex-dev MCP server (fastmcp on stdio)")
            return
        try:
            from .._mcp._server import mcp as mcp_server
        except ImportError as e:
            raise click.ClickException(
                f"Failed to import the MCP server. `fastmcp` is a BASE "
                f"dependency of scitex-dev, so a correct install always has "
                f"it — this means the environment is broken or partial, not "
                f"that a feature is missing. Reinstall into this "
                f"interpreter: `python -m pip install --force-reinstall "
                f"scitex-dev`.\n{e}"
            ) from e

        from scitex_logging import getLogger

        getLogger(__name__).info("Starting scitex-dev MCP server on stdio")
        mcp_server.run()

    @mcp.command(
        "doctor",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Check MCP server dependencies and configuration.",
            examples=(Example("{prog} mcp doctor", "Verify fastmcp + tool loading."),),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit a catalog/dependency diagnosis.")
    def mcp_doctor(as_json):
        from importlib import metadata

        versions = {}
        for package in ("fastmcp", "mcp"):
            try:
                versions[package] = metadata.version(package)
            except metadata.PackageNotFoundError:
                versions[package] = None
        result = {"versions": versions, "runtime_verified": False,
                  "client_loaded": False, "tools_discovered": 0}
        code = 0
        try:
            from .._mcp._server import mcp as mcp_server
            from .._ecosystem._mcp import get_tools_sync

            count = len(get_tools_sync(mcp_server))
            if not count:
                raise ValueError("MCP catalog contains no tools")
            result.update(status="catalog-available", tools_discovered=count)
        except Exception as exc:
            result.update(status="not-ready", error_type=type(exc).__name__,
                          detail=str(exc))
            code = 2
        if as_json:
            click.echo(json.dumps(result, indent=2))
        elif code:
            click.echo("MCP catalog unavailable: " + result["detail"], err=True)
            click.echo("Check the installed fastmcp/mcp dependency combination.", err=True)
        else:
            click.echo(f"MCP catalog available ({result['tools_discovered']} tools).")
            click.echo("Client loading, authorization and a stdio handshake remain separate.")
        if code:
            raise SystemExit(code)

    @mcp.command(
        "installation",
        hidden=True,
        context_settings={"ignore_unknown_options": True},
    )
    @click.pass_context
    def mcp_installation_deprecated(ctx):
        """(deprecated) Renamed to `install`."""
        click.echo(
            "error: `scitex-dev mcp installation` was renamed to "
            "`scitex-dev mcp install`.\n"
            "Re-run with: scitex-dev mcp install",
            err=True,
        )
        ctx.exit(2)

    @mcp.command(
        "show-installation",
        hidden=True,
        context_settings={"ignore_unknown_options": True},
    )
    @click.pass_context
    def mcp_show_installation_deprecated(ctx):
        """(deprecated) Renamed to `install`."""
        click.echo(
            "error: `scitex-dev mcp show-installation` was renamed to "
            "`scitex-dev mcp install`.\n"
            "Re-run with: scitex-dev mcp install",
            err=True,
        )
        ctx.exit(2)

    @mcp.command(
        "install",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Show MCP setup or merge it into an explicit JSON client config.",
            description=(
                "Without --config, only prints the leaf-owned setup manifest. "
                "With --config, merges this server while preserving foreign settings.",
            ),
            examples=(
                Example("{prog} mcp install", "Human-readable instructions."),
                Example("{prog} mcp install --json", "Machine-readable manifest."),
                Example("{prog} mcp install --config /tmp/owned-mcp.json --dry-run --json",
                        "Preview an explicit JSON client config merge."),
            ),
        ),
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help="Emit JSON manifest of MCP install instructions.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Preview an explicit --config merge without writing.",
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        help="Accepted for CLI consistency; conflicts are always refused.",
    )
    @click.option(
        "--config", type=click.Path(path_type=Path),
        help="Merge into this compatible JSON MCP client config; no default file is changed.",
    )
    def mcp_install(as_json, dry_run, yes, config):
        del yes
        from ..mcp_setup import build_mcp_install_manifest, install_mcp_client_config

        manifest = build_mcp_install_manifest(
            "scitex-dev", command="scitex-dev", args=("mcp", "start"),
            verify=(("scitex-dev", "mcp", "doctor", "--json"),
                    ("scitex-dev", "mcp", "list-tools", "--json")),
        )
        # Retain the former JSON keys as compatibility aliases; client_config
        # is the normalized fragment shared with leaf providers and consumers.
        manifest["install"] = "pip install scitex-dev"
        manifest["mcp_servers"] = manifest["client_config"]["mcpServers"]
        manifest["verify"] = ["scitex-dev mcp doctor", "scitex-dev mcp list-tools"]
        if config is not None:
            try:
                manifest["installation"] = install_mcp_client_config(
                    manifest["client_config"], config, dry_run=dry_run
                )
            except (ValueError, OSError) as exc:
                raise click.ClickException(str(exc)) from exc
        if as_json:
            click.echo(json.dumps(manifest, indent=2))
            return
        click.echo("Install scitex-dev (MCP support is in the base install):")
        click.echo("  pip install scitex-dev")
        click.echo("Compatible JSON MCP client configuration:")
        click.echo(json.dumps(manifest["client_config"], indent=2))
        if config is not None:
            click.echo(json.dumps(manifest["installation"], indent=2))
        click.echo("Client reload/authorization and runtime verification are separate.")
        click.echo("Verify: scitex-dev mcp doctor; scitex-dev mcp list-tools --json")

    @mcp.command(
        "list-tools",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List available MCP tools.",
            examples=(
                Example("{prog} mcp list-tools", "Tool names only."),
                Example("{prog} mcp list-tools -vv", "Names + descriptions."),
                Example("{prog} mcp list-tools --json", "Structured JSON output."),
            ),
        ),
    )
    @click.option(
        "-v", "--verbose", count=True, help="Verbosity: -v sig, -vv +desc, -vvv full."
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def mcp_list_tools(verbose, as_json):
        try:
            from .._mcp._server import mcp as mcp_server
        except ImportError as e:
            raise click.ClickException(
                f"fastmcp not installed. It is a BASE dependency of "
                f"scitex-dev, so this is a broken or partial install rather "
                f"than a missing feature. Reinstall into this interpreter: "
                f"`python -m pip install --force-reinstall scitex-dev`.\n{e}"
            ) from e

        from .._ecosystem._mcp import get_tools_sync

        tools = list(get_tools_sync(mcp_server).values())
        total = len(tools)

        if as_json:
            from .._core.types import RESULT_SCHEMA

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
                click.echo("    -> Result")
                click.echo()

    from ._knob_commands import add_knob_commands

    add_knob_commands(mcp, "mcp")

    return mcp


def _print_mcp_help_recursive(ctx: click.Context, mcp_grp: click.Group) -> None:
    fake_parent = click.Context(click.Group(), info_name="scitex-dev")
    parent_ctx = click.Context(mcp_grp, info_name="mcp", parent=fake_parent)

    click.secho("=== scitex-dev mcp ===", fg="cyan", bold=True)
    click.echo(mcp_grp.get_help(parent_ctx))

    for name in sorted(mcp_grp.list_commands(ctx) or []):
        cmd = mcp_grp.get_command(ctx, name)
        if cmd is None:
            continue
        click.echo()
        click.secho(f"=== scitex-dev mcp {name} ===", fg="cyan", bold=True)
        with click.Context(cmd, info_name=name, parent=parent_ctx) as sub_ctx:
            click.echo(cmd.get_help(sub_ctx))


# EOF
