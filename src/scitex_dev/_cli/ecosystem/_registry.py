#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI commands for ecosystem management -- registered on main CLI group."""

import json

import click


def register_ecosystem_commands(main_group):
    """Register ecosystem command group on the main CLI.

    Returns the ``ecosystem`` Click group so additional subcommands
    (stats, audit-frontmatter, audit-docs, audit-lines, audit-scope)
    can be registered on it from outside this module.
    """

    @main_group.group(invoke_without_command=True)
    @click.option(
        "--help-recursive", is_flag=True, help="Show help for all subcommands."
    )
    @click.pass_context
    def ecosystem(ctx, help_recursive):
        """Manage the SciTeX ecosystem (versions, sync, audits, stats)."""
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
        from ..._ecosystem import ECOSYSTEM, get_all_packages

        pkgs = list(package) if package else get_all_packages()

        if versions:
            from ... import list_versions
            from .._utils import wrap_as_cli

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

    @ecosystem.command("show-graph")
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
        from ..._ecosystem import _graph as _eg

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

    @ecosystem.command("check-versions")
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

        from ..._ecosystem._packages import packages_audit

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

    # Deprecated alias for the §1 noun-verb fix (packages → check-versions).
    # Removed in 0.11.0.
    @ecosystem.command(
        "packages",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def _ecosystem_packages_deprecated(ctx):
        """(deprecated) Use `ecosystem check-versions`. Removed in 0.11.0."""
        click.echo(
            "warning: `ecosystem packages` was renamed to `ecosystem check-versions`.",
            err=True,
        )
        target = ecosystem.get_command(ctx, "check-versions")
        if target is None:
            ctx.exit(2)
        ctx.invoke(target, *ctx.args)

    @ecosystem.command("fix-mismatches", hidden=True)
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
        from ... import fix_mismatches
        from .._utils import wrap_as_cli

        wrap_as_cli(fix_mismatches, as_json=as_json, confirm=confirm)

    @ecosystem.command("sync")
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--dry-run", is_flag=True, help="Preview without syncing.")
    @click.option(
        "--jobs",
        "-j",
        "jobs",
        default="1",
        show_default=True,
        help="Parallel installs. 1=serial, N=N workers, 0 or 'auto'=all CPUs.",
    )
    @click.option(
        "--quiet",
        "-q",
        is_flag=True,
        help="Suppress per-package progress lines (errors still on stderr).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    def ecosystem_sync(package, dry_run, jobs, quiet, as_json):
        """Install ecosystem packages from local clones in editable mode (pip install -e).

        Walks every configured package, runs `pip install -e <local_path>` for
        each. Use `-j N` to install in parallel; progress is streamed to stderr
        unless --json or --quiet is set.
        """
        import sys

        from .._utils import wrap_as_cli
        from ..._sync import sync_local

        pkgs = list(package) if package else None

        # Resolve --jobs ('auto' or '0' → all CPUs)
        if str(jobs).lower() in ("auto", "0"):
            jobs_n = 0
        else:
            try:
                jobs_n = int(jobs)
            except ValueError:
                click.echo(
                    f"error: --jobs must be int, 'auto', or '0' (got {jobs!r})",
                    err=True,
                )
                sys.exit(2)

        # Per-package progress callback (stderr; off in --json or --quiet mode)
        def _progress(idx, total, name, status, elapsed):
            mark = {"ok": "✓", "error": "✗", "skipped": "·", "dry_run": "·"}.get(
                status, "?"
            )
            click.echo(
                f"[{idx}/{total}] {mark} {name} ({status}, {elapsed:.1f}s)", err=True
            )

        on_progress = None if (as_json or quiet) else _progress

        wrap_as_cli(
            sync_local,
            as_json=as_json,
            packages=pkgs,
            confirm=not dry_run,
            jobs=jobs_n,
            on_progress=on_progress,
        )

    @ecosystem.command("sync-remote", hidden=True)
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
        from .._utils import wrap_as_cli
        from ..._sync import sync_all

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
            from ..audit._summary._audit import REGISTRY_CASCADE_DOC, _load_registry
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
        from ..audit import _summary as _cli_audit

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
        from ..audit._summary._mcp_audit import run_audit_mcp, run_audit_mcp_all

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
        from ..audit import _api as _cli_audit_api

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
        from ..audit import _skills as _cli_audit_skills

        raise SystemExit(
            _cli_audit_skills.audit_skills(
                distribution,
                json_out=json_out,
                rules=set(rules) if rules else None,
            )
        )

    @ecosystem.command(
        "audit-project",
        epilog=(
            "Project-structure auditor.\n"
            "\n"
            "Foundation rules (PS<§><idx>):\n"
            "  PS101–104  §1 top-level layout (pyproject, forbidden dirs, junk)\n"
            "  PS201–206  §2 src ↔ tests mirror (parent, mirror, prefix, orphan, placeholder)\n"
            "  PS301–303  §3 tests/ subdir convention (htmlcov, unknown subdirs, examples)\n"
            "  PS401–402  §4 docs/ structure (to_claude gitignored, assets location)\n"
            "\n"
            "See _skills/general/02_package_01_project-structure-root.md for the\n"
            "full convention; ditto _skills/scientific/02_research-project_01_project-structure-root.md\n"
            "for research-project layout. Templates and datasets are exempt from §2."
        ),
    )
    @click.argument("distribution")
    @click.option(
        "--repo",
        "repo_path",
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
        default=None,
        help="Repo root (defaults to the registry's local_path or the installed package's location).",
    )
    @click.option("--json", "json_out", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Restrict to specific rule codes (e.g. --rule PS201). Repeatable.",
    )
    def ecosystem_audit_project(distribution, repo_path, json_out, rules):
        """Check a package's project-structure against the canonical layout."""
        from pathlib import Path

        from ..audit import _project as _cli_audit_project
        from ..._ecosystem import ECOSYSTEM

        repo = Path(repo_path).expanduser() if repo_path else None
        if repo is None:
            local = ECOSYSTEM.get(distribution, {}).get("local_path")
            if local:
                cand = Path(local).expanduser()
                if cand.is_dir():
                    repo = cand

        raise SystemExit(
            _cli_audit_project.audit_project(
                distribution,
                repo=repo,
                json_out=json_out,
                rules=set(rules) if rules else None,
            )
        )

    # ------------------------------------------------------------------ #
    # audit-summary — cross-leaf, cross-auditor violation counts. The   #
    # one-command answer to "what's the deterministic state of the       #
    # ecosystem right now?" — re-runnable, replayable, immune to drift.  #
    # ------------------------------------------------------------------ #

    @ecosystem.command(
        "audit-summary",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-summary\n"
            "  $ scitex-dev ecosystem audit-summary --auditor python-apis\n"
            "  $ scitex-dev ecosystem audit-summary --json\n"
            "  $ scitex-dev ecosystem audit-summary --parallel 16\n"
            "\n"
            "Runs each scitex-dev auditor against every ecosystem leaf and\n"
            "prints per-leaf violation counts. Each rule is deterministic, so\n"
            "the same commit gives the same numbers across machines.\n"
            "\n"
            "Excluded by default: scitex (umbrella), scitex-orochi,\n"
            "scitex-cloud. Pass --include-meta to include them."
        ),
    )
    @click.option(
        "--auditor",
        "auditors",
        multiple=True,
        type=click.Choice(
            [
                "python-apis",
                "skills",
                "project",
                "cli",
                "mcp-tools",
            ]
        ),
        help="Auditor(s) to run. Repeatable. Default: all five.",
    )
    @click.option(
        "--jobs",
        "-j",
        "parallel",
        default=8,
        type=int,
        show_default=True,
        help="Concurrent leaves audited in parallel (-j auto / -j0 = all CPUs).",
    )
    @click.option(
        "--include-meta",
        is_flag=True,
        help="Include scitex / scitex-orochi / scitex-cloud (skipped by default).",
    )
    @click.option(
        "--json",
        "json_out",
        is_flag=True,
        help="Emit structured JSON instead of a table.",
    )
    def ecosystem_audit_summary(auditors, parallel, include_meta, json_out):
        """Cross-leaf, cross-auditor violation summary — one source of truth."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import subprocess
        from ..._ecosystem import ECOSYSTEM

        chosen = (
            list(auditors)
            if auditors
            else ["python-apis", "skills", "project", "cli", "mcp-tools"]
        )

        skip = set() if include_meta else {"scitex", "scitex-orochi", "scitex-cloud"}
        leaves = sorted(name for name in ECOSYSTEM.keys() if name not in skip)

        def _audit_one(leaf, auditor):
            """Subprocess one (leaf, auditor); return (leaf, auditor, n_violations)."""
            try:
                proc = subprocess.run(
                    [
                        "scitex-dev",
                        "ecosystem",
                        f"audit-{auditor}",
                        leaf,
                        "--json",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                # Auditors return non-zero on violations but still emit JSON.
                # Look for JSON in stdout regardless of exit code.
                payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
                violations = payload.get("violations", [])
                if not isinstance(violations, list):
                    violations = []
                return leaf, auditor, len(violations)
            except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
                return leaf, auditor, -1  # sentinel: error

        # Run all (leaf, auditor) pairs in a thread pool.
        results: dict[str, dict[str, int]] = {leaf: {} for leaf in leaves}
        pairs = [(leaf, a) for leaf in leaves for a in chosen]

        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = [pool.submit(_audit_one, leaf, a) for leaf, a in pairs]
            for fut in as_completed(futures):
                leaf, auditor, n = fut.result()
                results[leaf][auditor] = n

        if json_out:
            click.echo(
                json.dumps(
                    {
                        "auditors": chosen,
                        "leaves": leaves,
                        "violations": results,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return

        # Pretty table.
        col_w = 30
        click.secho(
            f"\n=== ecosystem audit-summary ({len(leaves)} leaves × {len(chosen)} auditors, parallel={parallel}) ===",
            fg="cyan",
            bold=True,
        )
        header = (
            f"{'PACKAGE':<{col_w}}" + "".join(f"{a:>14}" for a in chosen) + "  TOTAL"
        )
        click.echo(header)
        click.echo("-" * len(header))

        per_auditor_total = dict.fromkeys(chosen, 0)
        per_auditor_clean = dict.fromkeys(chosen, 0)
        leaf_total = 0

        for leaf in leaves:
            row = f"{leaf:<{col_w}}"
            row_total = 0
            row_has_violation = False
            for a in chosen:
                n = results[leaf].get(a, -1)
                if n < 0:
                    row += f"{'ERR':>14}"
                    continue
                row += f"{n:>14}"
                per_auditor_total[a] += n
                if n == 0:
                    per_auditor_clean[a] += 1
                else:
                    row_has_violation = True
                row_total += n
            row += f"  {row_total:>5}"
            leaf_total += row_total
            # Only print rows with violations, mirroring audit_snapshot.sh.
            if row_has_violation:
                click.echo(row)

        click.echo("-" * len(header))
        click.secho(
            f"{'TOTAL':<{col_w}}"
            + "".join(f"{per_auditor_total[a]:>14}" for a in chosen)
            + f"  {leaf_total:>5}",
            fg="yellow",
        )
        click.secho(
            f"{'CLEAN/N':<{col_w}}"
            + "".join(f"{per_auditor_clean[a]:>4}/{len(leaves):<9}" for a in chosen),
            fg="green",
        )

    @ecosystem.command(
        "audit-all",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-all scitex-io\n"
            "  $ scitex-dev ecosystem audit-all scitex-io --json\n"
            "\n"
            "Runs every audit-* command on a single distribution and\n"
            "aggregates exit codes (overall exit=1 if any auditor reports\n"
            "violations). For cross-leaf rollups across the whole ecosystem,\n"
            "use `audit-summary` instead."
        ),
    )
    @click.argument("distribution")
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--severity",
        type=click.Choice(["info", "warn", "error"]),
        default="warn",
        help="Minimum severity to report (passed through to each auditor).",
    )
    def ecosystem_audit_all(distribution, as_json, severity):
        """Run every audit-* on DISTRIBUTION; aggregate exit codes."""
        import json as _json
        import subprocess
        import sys as _sys

        # Order: cheap-to-fast → slow. Each audit-* honours --json + --severity
        # idempotently. audit-summary excluded — it's the cross-leaf rollup.
        audits = [
            "audit-cli",
            "audit-mcp-tools",
            "audit-skills",
            "audit-python-apis",
            "audit-project",
        ]

        results: dict = {}
        overall_exit = 0
        # Resolve sibling `scitex-dev` console script. Falls back to PATH lookup.
        import shutil as _shutil

        scitex_dev_bin = _shutil.which("scitex-dev") or "scitex-dev"
        for a in audits:
            cmd = [scitex_dev_bin, "ecosystem", a, distribution]
            if as_json:
                cmd.append("--json")
            # audit-cli + audit-summary support --severity; others ignore unknowns
            if a == "audit-cli":
                cmd += ["--severity", severity]
            try:
                if as_json:
                    r = subprocess.run(cmd, capture_output=True, text=True)
                    payload = r.stdout.strip() or "null"
                    try:
                        results[a] = {
                            "exit": r.returncode,
                            "data": _json.loads(payload),
                        }
                    except _json.JSONDecodeError:
                        results[a] = {"exit": r.returncode, "raw": payload}
                else:
                    click.echo(f"\n=== {a} ===", err=True)
                    r = subprocess.run(cmd)
                    results[a] = {"exit": r.returncode}
            except Exception as e:
                click.echo(f"error: {a} failed to launch: {e}", err=True)
                results[a] = {"exit": 1, "error": str(e)}
                overall_exit = 1
                continue
            if r.returncode != 0:
                overall_exit = 1

        if as_json:
            click.echo(
                _json.dumps(
                    {"distribution": distribution, "results": results}, indent=2
                )
            )
        _sys.exit(overall_exit)

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
            from ...dashboard.app import run_background

            run_background(host=host, port=port, force=force)
            click.echo(f"Dashboard started in background on {host}:{port}")
        else:
            from ...dashboard import run_dashboard

            run_dashboard(
                port=port,
                host=host,
                debug=debug,
                open_browser=not no_browser,
                force=force,
            )

    return ecosystem
