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

    @ecosystem.command("graph")
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
    @click.pass_context
    def ecosystem_graph(ctx, fmt, output, cycles, include_extras, group_by_tier):
        """Emit a current-state ecosystem dependency graph (mermaid/DOT)."""
        from . import ecosystem_graph as _eg

        pkgs = _eg.discover_packages()
        graph = _eg.build_graph(pkgs)

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

    @ecosystem.command("packages")
    @click.option(
        "--host",
        "-h",
        "hosts",
        multiple=True,
        help="Host name(s). Default: all enabled hosts.",
    )
    @click.option(
        "--package",
        "-p",
        "packages",
        multiple=True,
        help="Package name(s). Default: all.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Mode 2: print commands that would run on out-of-sync hosts.",
    )
    @click.option(
        "--apply",
        "do_apply",
        is_flag=True,
        help="Mode 3: actually execute the sync. Mutually exclusive with --dry-run.",
    )
    @click.option(
        "--unsafe",
        is_flag=True,
        help="Skip ahead-check; allow clobbering remote unpushed commits.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.pass_context
    def ecosystem_packages(ctx, hosts, packages, dry_run, do_apply, unsafe, as_json):
        """Audit ecosystem package versions across hosts (3 modes).

        \b
            scitex-dev ecosystem packages                  # observe
            scitex-dev ecosystem packages --dry-run        # preview sync
            scitex-dev ecosystem packages --apply          # execute sync
        """
        if dry_run and do_apply:
            click.echo("error: --dry-run and --apply are mutually exclusive", err=True)
            ctx.exit(2)

        from .ecosystem_packages import packages_audit

        host_list = list(hosts) if hosts else None
        pkg_list = list(packages) if packages else None
        if host_list == ["all"]:
            host_list = None

        if do_apply:
            mode = "apply"
        elif dry_run:
            mode = "dry-run"
        else:
            mode = "observe"

        result = packages_audit(
            mode=mode, hosts=host_list, packages=pkg_list, unsafe=unsafe
        )

        if as_json:
            # Drop the rendered table from JSON; "state" is the structured form.
            payload = {k: v for k, v in result.items() if k != "table"}
            click.echo(json.dumps(payload, indent=2, default=str))
        else:
            if mode == "observe":
                click.echo(result["table"])
                summ = result["summary"]
                click.echo()
                click.echo(f"{summ['matching']}/{summ['total']} cells up-to-date")
                if summ["needing_sync"]:
                    click.echo("needing sync:")
                    for n in summ["needing_sync"]:
                        click.echo(f"  - {n['host']}: {n['pkg']}")
            elif mode == "dry-run":
                cmds = result["commands"]
                if not cmds:
                    click.echo("# everything in sync — no commands to preview")
                for host, pkgs_ in cmds.items():
                    for pkg, lines in pkgs_.items():
                        click.echo(f"# {host} :: {pkg}")
                        for line in lines:
                            click.echo(f"  {line}")
            else:  # apply
                click.echo(json.dumps(result, indent=2, default=str))

        # Exit code: observe returns 1 if anything mismatches (or unknown).
        if mode == "observe":
            summ = result["summary"]
            ctx.exit(
                0 if summ["matching"] == summ["total"] and summ["total"] > 0 else 1
            )
        ctx.exit(0)

    @ecosystem.command("fix-mismatches")
    @click.option(
        "--confirm", is_flag=True, help="Apply fixes (default: preview only)."
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.pass_context
    def ecosystem_fix_mismatches(ctx, confirm, as_json):
        """(deprecated) Renamed to `packages`. Forwards to `packages [--apply]`."""
        click.echo(
            "warning: `ecosystem fix-mismatches` is deprecated; "
            "use `ecosystem packages` (or `packages --apply` to execute).",
            err=True,
        )
        from . import fix_mismatches
        from .cli_utils import wrap_as_cli

        wrap_as_cli(fix_mismatches, as_json=as_json, confirm=confirm)

    @ecosystem.command("sync")
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--dry-run", is_flag=True, help="Preview without syncing.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def ecosystem_sync(package, dry_run, as_json):
        """Sync ecosystem packages locally (pip install -e)."""
        from .cli_utils import wrap_as_cli
        from .sync import sync_local

        pkgs = list(package) if package else None
        wrap_as_cli(sync_local, as_json=as_json, packages=pkgs, confirm=not dry_run)

    @ecosystem.command("sync-remote")
    @click.option(
        "--host",
        "-h",
        "hosts",
        multiple=True,
        help="Host name(s). Omit or pass 'all' to sync every enabled host.",
    )
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--dry-run", is_flag=True, help="Preview without syncing.")
    @click.option(
        "--unsafe",
        is_flag=True,
        help="Disable the ahead-check; allow clobbering unpushed remote commits.",
    )
    @click.option(
        "--no-install", is_flag=True, help="Skip pip install -e . after git pull."
    )
    @click.option("--no-stash", is_flag=True, help="Skip git stash / stash pop wrap.")
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def ecosystem_sync_remote(
        hosts, package, dry_run, unsafe, no_install, no_stash, as_json
    ):
        """(deprecated) Sync ecosystem packages to remote hosts over SSH.

        Replaced by ``ecosystem packages`` (default observation mode,
        ``--dry-run`` preview, ``--apply`` to execute). This alias will
        be removed in the next major release.

        Each package on each host is: ahead-check -> git stash -> git
        pull -> pip install -e . -> git stash pop. Packages whose
        remote working copy has unpushed commits are skipped by
        default (safety).

        Examples:

        \b
            scitex-dev ecosystem sync-remote --dry-run
            scitex-dev ecosystem sync-remote -h mba -h spartan
            scitex-dev ecosystem sync-remote -h all -p scitex-db
        """
        click.echo(
            "warning: `ecosystem sync-remote` is deprecated; "
            "use `ecosystem packages` (default observation, --dry-run preview, "
            "--apply to execute).",
            err=True,
        )
        from .cli_utils import wrap_as_cli
        from .sync import sync_all

        host_list = list(hosts) if hosts else None
        if host_list == ["all"]:
            host_list = None
        pkgs = list(package) if package else None
        wrap_as_cli(
            sync_all,
            as_json=as_json,
            hosts=host_list,
            packages=pkgs,
            stash=not no_stash,
            install=not no_install,
            safe=not unsafe,
            confirm=not dry_run,
        )

    @ecosystem.command(
        "dashboard",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def ecosystem_dashboard_deprecated(ctx):
        """(deprecated) Renamed to `start-dashboard`."""
        click.echo(
            "error: `scitex-dev ecosystem dashboard` was renamed to "
            "`scitex-dev ecosystem start-dashboard`.\n"
            "Re-run with: scitex-dev ecosystem start-dashboard [...]",
            err=True,
        )
        ctx.exit(2)

    def _audit_cli_epilog() -> str:
        """Build a dynamic --help epilog showing the registry cascade + entries."""
        try:
            from ._cli_audit._audit import REGISTRY_CASCADE_DOC, _load_registry
        except Exception:
            return ""
        registry, provenance = _load_registry(None)
        # Group by category
        from collections import defaultdict

        groups: dict[str, list[str]] = defaultdict(list)
        for name, info in registry.items():
            groups[info.get("category", "uncategorized")].append(name)

        # Click rewraps epilog paragraphs; prefix each preserved paragraph
        # with `\b` so Click leaves whitespace alone.
        lines: list[str] = ["\b", REGISTRY_CASCADE_DOC.rstrip(), ""]
        lines.append("\b")
        lines.append(f"Resolved registry source: {provenance}")
        lines.append("")
        lines.append("\b")
        lines.append("Registry contents (used by --all):")
        for cat in sorted(groups):
            lines.append(f"  [{cat}] ({len(groups[cat])})")
            for n in sorted(groups[cat]):
                lines.append(f"    {n}")
        lines.append("")
        lines.append("\b")
        lines.append("Examples:")
        lines.append("  $ scitex-dev ecosystem audit-cli scitex-plt")
        lines.append("  $ scitex-dev ecosystem audit-cli scitex-plt --behavioral")
        lines.append("  $ scitex-dev ecosystem audit-cli --all")
        lines.append("  $ scitex-dev ecosystem audit-cli --all --json > drift.json")
        lines.append(
            "  $ scitex-dev ecosystem audit-cli --all --dry-run   # list targets only"
        )
        return "\n".join(lines)

    @ecosystem.command(
        "audit-cli",
        epilog=_audit_cli_epilog(),
    )
    @click.argument("package", required=False)
    @click.option(
        "--all",
        "audit_all",
        is_flag=True,
        help="Audit every package in the resolved registry (see epilog for the cascade).",
    )
    @click.option(
        "--behavioral",
        is_flag=True,
        help="Run subprocess-based checks (§1a -v ladder, §3 exit codes, §8 --json stdout). Slow.",
    )
    @click.option(
        "--json",
        "output_json",
        is_flag=True,
        help="Machine-readable JSON output on stdout (per §2 / §8).",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="With --all: list the targets that would be audited; do nothing else.",
    )
    @click.option(
        "--registry",
        "registry_path",
        default=None,
        type=click.Path(dir_okay=False),
        help="Override the registry source (highest precedence in the cascade).",
    )
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Only report violations of this rule (e.g. --rule §1a). Repeatable.",
    )
    @click.option(
        "--exclude",
        "exclude_rules",
        multiple=True,
        help="Suppress this rule (e.g. --exclude §4). Repeatable.",
    )
    @click.option(
        "--severity",
        "min_severity",
        type=click.Choice(["info", "warn", "error"], case_sensitive=False),
        default=None,
        help="Only report violations at or above this severity.",
    )
    @click.option(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-package subprocess timeout (seconds) for behavioral checks.",
    )
    def ecosystem_audit_cli(
        package,
        audit_all,
        behavioral,
        output_json,
        dry_run,
        registry_path,
        rules,
        exclude_rules,
        min_severity,
        timeout,
    ):
        """Check a package's CLI against the noun-verb convention (warn-only).

        Requires the `cli-audit` extra: pip install 'scitex-dev[cli-audit]'

        The package list for --all is resolved via the registry cascade
        documented in the epilog below.
        """
        from . import _cli_audit

        raise SystemExit(
            _cli_audit.audit_cli(
                package=package,
                behavioral=behavioral,
                output_json=output_json,
                audit_all=audit_all,
                dry_run=dry_run,
                registry_path=registry_path,
                rules=tuple(rules),
                exclude=tuple(exclude_rules),
                min_severity=min_severity,
                timeout=timeout,
            )
        )

    # ------------------------------------------------------------------ #
    # audit-mcp-tools — companion to audit-cli for MCP servers           #
    # ------------------------------------------------------------------ #

    @ecosystem.command(
        "audit-mcp-tools",
        epilog=(
            "\b\nRules audited (per scitex `_skills/general/03_interface_03_mcp/`):\n"
            "\b\n"
            "  §1  server registration (single FastMCP, mount pattern, no double prefix)\n"
            "  §2  tool naming `<pkg>_<verb>_<noun>` snake_case\n"
            "  §3  required `mcp` subcommands (start | doctor | list-tools | show-installation)\n"
            "  §4  `mcp list-tools` -v|-vv|-vvv + --json (behavioral)\n"
            "  §5  `<pkg>_skills_list` and `<pkg>_skills_get` present\n"
            "  §6  Python-API ↔ MCP-tool parity\n"
            "\n"
            "\b\nExamples:\n"
            "  $ scitex-dev ecosystem audit-mcp-tools scitex-cloud\n"
            "  $ scitex-dev ecosystem audit-mcp-tools scitex-cloud --behavioral\n"
            "  $ scitex-dev ecosystem audit-mcp-tools --all --json > mcp-drift.json"
        ),
    )
    @click.argument("package", required=False)
    @click.option(
        "--all",
        "audit_all",
        is_flag=True,
        help="Audit every MCP-bearing package in the resolved registry.",
    )
    @click.option(
        "--behavioral",
        is_flag=True,
        help="Run subprocess-based checks (§3 mcp subcommands, §4 ladder + --json). Slow.",
    )
    @click.option(
        "--json",
        "output_json",
        is_flag=True,
        help="Machine-readable JSON output on stdout.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="With --all: list the targets that would be audited; do nothing else.",
    )
    @click.option(
        "--registry",
        "registry_path",
        default=None,
        type=click.Path(dir_okay=False),
        help="Override the registry source (highest precedence in the cascade).",
    )
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Only report violations of this rule (e.g. --rule §2). Repeatable.",
    )
    @click.option(
        "--exclude",
        "exclude_rules",
        multiple=True,
        help="Suppress this rule (e.g. --exclude §6). Repeatable.",
    )
    @click.option(
        "--severity",
        "min_severity",
        type=click.Choice(["info", "warn", "error"], case_sensitive=False),
        default=None,
        help="Only report violations at or above this severity.",
    )
    @click.option(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-package subprocess timeout (seconds) for behavioral checks.",
    )
    def ecosystem_audit_mcp_tools(
        package,
        audit_all,
        behavioral,
        output_json,
        dry_run,
        registry_path,
        rules,
        exclude_rules,
        min_severity,
        timeout,
    ):
        """Check a package's MCP server against the canonical convention (warn-only).

        Requires the `cli-audit` extra: pip install 'scitex-dev[cli-audit]'

        The package list for --all is resolved via the same registry cascade
        used by `audit-cli` (see that command's --help).
        """
        from ._cli_audit._mcp_audit import run_audit_mcp, run_audit_mcp_all

        if audit_all:
            raise SystemExit(
                run_audit_mcp_all(
                    behavioral=behavioral,
                    output_json=output_json,
                    dry_run=dry_run,
                    registry_path=registry_path,
                    rules=tuple(rules),
                    exclude=tuple(exclude_rules),
                    min_severity=min_severity,
                    timeout=timeout,
                )
            )
        if package is None:
            click.echo("error: PACKAGE is required (or pass --all)", err=True)
            raise SystemExit(2)
        raise SystemExit(
            run_audit_mcp(
                package,
                behavioral=behavioral,
                output_json=output_json,
                rules=tuple(rules),
                exclude=tuple(exclude_rules),
                min_severity=min_severity,
                timeout=timeout,
            )
        )

    # ------------------------------------------------------------------ #
    # audit-python-apis — companion to audit-cli / audit-mcp-tools for    #
    # the Python API surface (mirrors `list-python-apis` introspection)   #
    # ------------------------------------------------------------------ #

    @ecosystem.command(
        "audit-python-apis",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-python-apis scitex-io\n"
            "  $ scitex-dev ecosystem audit-python-apis scitex-io --json\n"
            "  $ scitex-dev ecosystem audit-python-apis scitex-io --rule PA101 --rule PA202\n"
            "\n"
            "Foundation rules (PA<§><idx>): PA101–104 (§1 naming/visibility),\n"
            "PA201–203 (§2 version), PA301 (§3 lazy imports), PA501 (§5 future\n"
            "annotations). See general/03_interface_01_python-api/12_audit-checklist.md."
        ),
    )
    @click.argument("distribution")
    @click.option("--json", "json_out", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Restrict to specific rule codes (e.g. --rule PA101). Repeatable.",
    )
    def ecosystem_audit_python_apis(distribution, json_out, rules):
        """Check a package's Python API against the §1–§5 audit checklist."""
        from . import _cli_audit_api

        raise SystemExit(
            _cli_audit_api.audit_api(
                distribution,
                json_out=json_out,
                rules=set(rules) if rules else None,
            )
        )

    # ------------------------------------------------------------------ #
    # audit-skills — companion to audit-cli / audit-mcp-tools / audit-   #
    # python-apis for the `_skills/<pip-name>/` tree                      #
    # ------------------------------------------------------------------ #

    @ecosystem.command(
        "audit-skills",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-skills scitex-io\n"
            "  $ scitex-dev ecosystem audit-skills scitex-io --json\n"
            "  $ scitex-dev ecosystem audit-skills scitex-io --rule SK210 --rule SK211\n"
            "\n"
            "Foundation rules (SK<§><idx>): SK101–104 (§1 layout), SK201–203\n"
            "(§2 naming), SK210–211 (§2a no header/footer above frontmatter),\n"
            "SK301–302 (§3 SKILL.md as index), SK401 (§4 leaf size), SK601\n"
            "(§6 no `import scitex as stx`), SK701–704 (frontmatter required\n"
            "fields). See general/03_interface_04_skills/12_quality-checklist.md."
        ),
    )
    @click.argument("distribution")
    @click.option("--json", "json_out", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Restrict to specific rule codes (e.g. --rule SK210). Repeatable.",
    )
    def ecosystem_audit_skills(distribution, json_out, rules):
        """Check a package's `_skills/<pip-name>/` against the §1–§FM checklist."""
        from . import _cli_audit_skills

        raise SystemExit(
            _cli_audit_skills.audit_skills(
                distribution,
                json_out=json_out,
                rules=set(rules) if rules else None,
            )
        )

    @ecosystem.command("start-dashboard")
    @click.option("--port", default=8050, type=int, help="Port to serve on.")
    @click.option("--host", default="0.0.0.0", help="Host to bind to.")
    @click.option("--debug", is_flag=True, help="Enable debug/reload mode.")
    @click.option(
        "--no-browser", is_flag=True, help="Do not open browser automatically."
    )
    @click.option("--force", is_flag=True, help="Kill existing process on the port.")
    @click.option(
        "--background", is_flag=True, help="Run dashboard in a background process."
    )
    def ecosystem_start_dashboard(port, host, debug, no_browser, force, background):
        """Launch the ecosystem dashboard web UI."""
        if background:
            # Delegate to run_background so log + pid land under
            # ~/.scitex/dev/runtime/ per 01_arch_06_local-state-directories.md.
            from .dashboard.app import run_background

            run_background(host=host, port=port, force=force)
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
