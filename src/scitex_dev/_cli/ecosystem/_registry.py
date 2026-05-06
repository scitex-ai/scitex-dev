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
        """List packages in the SciTeX ecosystem.

        \b
        Example:
            $ scitex-dev ecosystem list
            $ scitex-dev ecosystem list --json
            $ scitex-dev ecosystem list -p scitex-io --versions
        """
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
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit graph as JSON edges/nodes."
    )
    @click.pass_context
    def ecosystem_graph(
        ctx, fmt, output, cycles, include_extras, group_by_tier, as_json
    ):
        """Emit a current-state ecosystem dependency graph (mermaid/DOT).

        \b
        Example:
            $ scitex-dev ecosystem show-graph
            $ scitex-dev ecosystem show-graph --format dot -o /tmp/eco.dot
            $ scitex-dev ecosystem show-graph --cycles
            $ scitex-dev ecosystem show-graph --json
        """
        from ..._ecosystem import _graph as _eg

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
        Example:
            $ scitex-dev ecosystem check-versions                  # observe
            $ scitex-dev ecosystem check-versions --dry-run        # preview sync
            $ scitex-dev ecosystem check-versions --apply          # execute sync
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
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def ecosystem_sync(package, dry_run, jobs, quiet, as_json, yes):
        """Install ecosystem packages from local clones in editable mode (pip install -e).

        Walks every configured package, runs `pip install -e <local_path>` for
        each. Use `-j N` to install in parallel; progress is streamed to stderr
        unless --json or --quiet is set.

        \b
        Example:
            $ scitex-dev ecosystem sync --dry-run
            $ scitex-dev ecosystem sync -y -j 4
            $ scitex-dev ecosystem sync -p scitex-io --yes
        """
        del yes  # accepted for §2 compliance; sync is non-interactive already
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

    # ---------------------------------------------------------------
    # Bootstrap / cross-machine ops: clone | checkout | pull | install
    # ---------------------------------------------------------------

    def _git_progress(idx, total, name, status, msg):
        mark = {"ok": "✓", "err": "✗", "skip": "·", "dry": "·"}.get(status, "?")
        click.echo(f"[{idx}/{total}] {mark} {name}: {msg}", err=True)

    @ecosystem.command("clone")
    @click.option("--dest", default="~/proj", show_default=True, help="Parent dir.")
    @click.option("--branch", default="develop", show_default=True)
    @click.option("--https", is_flag=True, help="Use https:// URLs (default ssh).")
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--jobs", "-j", default=4, show_default=True, type=int)
    @click.option(
        "--dry-run",
        is_flag=True,
        default=True,
        help="(default) Print what would run; do nothing. Pass --yes to apply.",
    )
    @click.option("--json", "as_json", is_flag=True)
    @click.option(
        "--yes", "-y", is_flag=True, help="Apply for real (overrides default dry-run)."
    )
    def ecosystem_clone(dest, branch, https, package, jobs, dry_run, as_json, yes):
        """Clone every ecosystem repo into DEST (default ~/proj/).

        \b
        Default is dry-run — pass --yes to actually clone.

        \b
        Example:
          $ scitex-dev ecosystem clone                # preview (dry-run)
          $ scitex-dev ecosystem clone --yes          # apply
          $ scitex-dev ecosystem clone --dest /scratch/proj --yes
          $ scitex-dev ecosystem clone --https --branch main --yes
          $ scitex-dev ecosystem clone -p scitex-io --yes
        """
        from pathlib import Path as _Path

        from ..._ecosystem._git_ops import clone_all

        # Dry-run is default; --yes overrides to apply for real.
        effective_dry_run = dry_run and not yes
        results = clone_all(
            dest=_Path(dest),
            branch=branch,
            use_ssh=not https,
            packages=list(package) or None,
            jobs=jobs,
            dry_run=effective_dry_run,
            on_progress=None if as_json else _git_progress,
        )
        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {k: {"exit": v[0], "msg": v[1]} for k, v in results.items()},
                    indent=2,
                )
            )
        rc = 0 if all(v[0] == 0 for v in results.values()) else 1
        raise SystemExit(rc)

    @ecosystem.command("checkout")
    @click.argument("branch")
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=True,
        help="(default) Print what would run; do nothing. Pass --yes to apply.",
    )
    @click.option(
        "--yes", "-y", is_flag=True, help="Apply for real (overrides default dry-run)."
    )
    @click.option("--json", "as_json", is_flag=True)
    def ecosystem_checkout(branch, package, dry_run, yes, as_json):
        """`git checkout <branch>` in every ecosystem clone.

        \b
        Default is dry-run — pass --yes to actually checkout.

        \b
        Example:
          $ scitex-dev ecosystem checkout develop          # preview
          $ scitex-dev ecosystem checkout develop --yes    # apply
          $ scitex-dev ecosystem checkout main -p scitex-io --yes
        """
        from ..._ecosystem._core import ECOSYSTEM as _ECO
        from ..._ecosystem._git_ops import checkout_all

        if dry_run and not yes:
            for n, info in _ECO.items():
                if info.get("archived") or (package and n not in package):
                    continue
                click.echo(f"would run in {info['local_path']}: git checkout {branch}")
            raise SystemExit(0)
        results = checkout_all(
            branch=branch,
            packages=list(package) or None,
            on_progress=None if as_json else _git_progress,
        )
        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {k: {"exit": v[0], "msg": v[1]} for k, v in results.items()},
                    indent=2,
                )
            )
        rc = 0 if all(v[0] == 0 for v in results.values()) else 1
        raise SystemExit(rc)

    @ecosystem.command("pull")
    @click.option(
        "--no-rebase", is_flag=True, help="Use plain git pull (default --rebase)."
    )
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--jobs", "-j", default=4, show_default=True, type=int)
    @click.option(
        "--dry-run",
        is_flag=True,
        default=True,
        help="(default) Print what would run; do nothing. Pass --yes to apply.",
    )
    @click.option(
        "--yes", "-y", is_flag=True, help="Apply for real (overrides default dry-run)."
    )
    @click.option("--json", "as_json", is_flag=True)
    def ecosystem_pull(no_rebase, package, jobs, dry_run, yes, as_json):
        """`git pull --rebase` in every ecosystem clone (parallel).

        \b
        Default is dry-run — pass --yes to actually pull.

        \b
        Example:
          $ scitex-dev ecosystem pull              # preview
          $ scitex-dev ecosystem pull --yes        # apply
          $ scitex-dev ecosystem pull --yes -j 8
          $ scitex-dev ecosystem pull -p scitex-io --yes
        """
        from ..._ecosystem._git_ops import pull_all

        if dry_run and not yes:
            from ..._ecosystem._core import ECOSYSTEM as _ECO

            for n, info in _ECO.items():
                if info.get("archived") or (package and n not in package):
                    continue
                cmd = "git pull" + ("" if no_rebase else " --rebase")
                click.echo(f"would run in {info['local_path']}: {cmd}")
            raise SystemExit(0)
        results = pull_all(
            rebase=not no_rebase,
            packages=list(package) or None,
            jobs=jobs,
            on_progress=None if as_json else _git_progress,
        )
        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {k: {"exit": v[0], "msg": v[1]} for k, v in results.items()},
                    indent=2,
                )
            )
        rc = 0 if all(v[0] == 0 for v in results.values()) else 1
        raise SystemExit(rc)

    @ecosystem.command("install")
    @click.option(
        "--source",
        type=click.Choice(["editable", "pypi"]),
        default="editable",
        show_default=True,
        help="editable: pip install -e <local>; pypi: pip install <name> from PyPI.",
    )
    @click.option("--extras", default="", help="Comma-separated extras (e.g. dev,mcp).")
    @click.option("--package", "-p", multiple=True, help="Specific packages.")
    @click.option("--jobs", "-j", default=1, show_default=True, type=int)
    @click.option(
        "--dry-run",
        is_flag=True,
        default=True,
        help="(default) Print what would run; do nothing. Pass --yes to apply.",
    )
    @click.option("--json", "as_json", is_flag=True)
    @click.option(
        "--yes", "-y", is_flag=True, help="Apply for real (overrides default dry-run)."
    )
    def ecosystem_install(source, extras, package, jobs, dry_run, as_json, yes):
        """`pip install` every ecosystem package.

        \b
        Default is dry-run — pass --yes to actually install.

        \b
        Example:
          $ scitex-dev ecosystem install                       # preview (dry-run)
          $ scitex-dev ecosystem install --yes                 # editable from local
          $ scitex-dev ecosystem install --source pypi --yes
          $ scitex-dev ecosystem install --extras dev,mcp -j 4 --yes
          $ scitex-dev ecosystem install -p scitex-io --source pypi --yes
        """
        from ..._ecosystem._git_ops import install_all

        # Dry-run is default; --yes overrides to apply for real.
        effective_dry_run = dry_run and not yes
        results = install_all(
            source=source,
            extras=extras,
            packages=list(package) or None,
            jobs=jobs,
            dry_run=effective_dry_run,
            on_progress=None if as_json else _git_progress,
        )
        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {k: {"exit": v[0], "msg": v[1]} for k, v in results.items()},
                    indent=2,
                )
            )
        rc = 0 if all(v[0] == 0 for v in results.values()) else 1
        raise SystemExit(rc)

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
    @click.option(
        "--fix",
        is_flag=True,
        help=(
            "Auto-fix mechanically resolvable rules (SK705/SK709/SK710). "
            "Rewrites only frontmatter; idempotent."
        ),
    )
    def ecosystem_audit_skills(distribution, json_out, rules, fix):
        """Check a package's `_skills/<pip-name>/` against the §1–§FM checklist."""
        from ..audit import _skills as _cli_audit_skills

        raise SystemExit(
            _cli_audit_skills.audit_skills(
                distribution,
                json_out=json_out,
                rules=set(rules) if rules else None,
                fix=fix,
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
    @click.option(
        "--severity",
        type=click.Choice(["error", "warning", "info"]),
        default="error",
        show_default=True,
        help=(
            "Minimum severity floor. 'error' prints E findings only and exits 1 "
            "iff ≥1 E. 'warning' prints E+W. 'info' prints everything. "
            "W/I findings never fail CI on their own."
        ),
    )
    def ecosystem_audit_project(distribution, repo_path, json_out, rules, severity):
        """Check a package's project-structure against the canonical layout.

        \b
        Example:
            $ scitex-dev ecosystem audit-project scitex-io
            $ scitex-dev ecosystem audit-project scitex-dev --json
            $ scitex-dev ecosystem audit-project scitex-stats --rule PS108
            $ scitex-dev ecosystem audit-project scitex-io --severity warning
        """
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
                severity=severity,
            )
        )

    # ------------------------------------------------------------------ #
    # init-config — write a `.scitex/dev/config.yaml` from the heuristic #
    # so the user can confirm + commit the project's type.               #
    # ------------------------------------------------------------------ #
    @ecosystem.command("init-config")
    @click.option(
        "--repo",
        "repo_path",
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
        default=".",
        show_default=True,
        help="Project root (defaults to cwd).",
    )
    @click.option(
        "--project-type",
        "project_types",
        multiple=True,
        type=click.Choice(["pip", "research"]),
        help="Override the heuristic guess. Repeatable for hybrid repos.",
    )
    @click.option(
        "--force",
        is_flag=True,
        help="Overwrite an existing .scitex/dev/config.yaml.",
    )
    @click.option("--yes", "-y", is_flag=True, help="Confirm destructive write.")
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the target path and detected project types without writing.",
    )
    def ecosystem_init_config(repo_path, project_types, force, yes, dry_run):
        """Write `.scitex/dev/config.yaml` from the heuristic guess.

        \b
        Example:
            $ scitex-dev ecosystem init-config
            $ scitex-dev ecosystem init-config --project-type research --yes
            $ scitex-dev ecosystem init-config --project-type pip --project-type research
            $ scitex-dev ecosystem init-config --dry-run
        """
        del yes  # accepted for §2 compliance; --force gates overwrite
        from pathlib import Path

        from ..audit._config import detect_project_types, write_config

        repo = Path(repo_path).expanduser().resolve()
        types = (
            list(project_types) if project_types else sorted(detect_project_types(repo))
        )
        if dry_run:
            target = repo / ".scitex" / "dev" / "config.yaml"
            click.echo(f"# would write: {target}  (project-type: {', '.join(types)})")
            return
        try:
            written = write_config(repo, project_types=types, overwrite=force)
        except FileExistsError as e:
            click.echo(
                f"refuse: {e} already exists; pass --force to overwrite.",
                err=True,
            )
            raise SystemExit(1)
        click.echo(f"wrote: {written}  (project-type: {', '.join(types)})")

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
        import os as _os
        import shutil as _shutil

        # Suppress per-auditor disclaimer; emit once at end of audit-all.
        sub_env = {**_os.environ, "SCITEX_DEV_NO_AUDIT_DISCLAIMER": "1"}
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
                    r = subprocess.run(cmd, capture_output=True, text=True, env=sub_env)
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
                    r = subprocess.run(cmd, env=sub_env)
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
        else:
            from ..._audit_disclaimer import emit_disclaimer, emit_skill_hints

            click.echo("", err=True)
            emit_disclaimer()
            # When at least one sub-auditor reported errors, append the
            # rule-prefix → skill-tree map. Per-auditor hints are
            # suppressed inside subprocess via SCITEX_DEV_NO_AUDIT_DISCLAIMER=1
            # so they don't fire five times — emit once at the end here.
            if overall_exit:
                emit_skill_hints()
        _sys.exit(overall_exit)

    @ecosystem.command(
        "write-audit-test",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem write-audit-test scitex-types\n"
            "  $ scitex-dev ecosystem write-audit-test scitex-io --force\n"
            "  $ scitex-dev ecosystem write-audit-test scitex-io --dry-run\n"
            "\n"
            "Drops the canonical pytest stub at\n"
            "`tests/develop/test_audit.py` so the package's own test\n"
            "suite runs `scitex-dev ecosystem audit-all <pkg>` and\n"
            "fails when any error-severity violation is reported. A\n"
            "separate `.github/workflows/audit.yml` is therefore not\n"
            "needed — the existing test workflow picks the audit up.\n"
            "Also creates `tests/develop/__init__.py` and an empty\n"
            "`tests/conftest.py` if either is missing."
        ),
    )
    @click.argument("distribution")
    @click.option("--force", is_flag=True, help="Overwrite an existing test_audit.py.")
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the target paths and contents without writing.",
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def ecosystem_write_audit_test(distribution, force, dry_run, yes):
        """Materialise tests/develop/test_audit.py for DISTRIBUTION."""
        del yes  # generation is non-destructive when --force is absent
        from ..._ecosystem import ECOSYSTEM, get_local_path

        if distribution not in ECOSYSTEM:
            click.echo(f"error: '{distribution}' not in ECOSYSTEM", err=True)
            raise SystemExit(2)
        info = ECOSYSTEM[distribution]
        if info.get("archived"):
            click.echo(f"skip  {distribution}: archived", err=True)
            raise SystemExit(0)

        local = get_local_path(distribution)
        if local is None or not local.exists():
            click.echo(
                f"error: local path for '{distribution}' missing: {local}",
                err=True,
            )
            raise SystemExit(2)

        tests = local / "tests"
        develop = tests / "develop"
        target = develop / "test_audit.py"
        develop_init = develop / "__init__.py"
        conftest = tests / "conftest.py"

        test_content = (
            '"""Audit conformance — runs `scitex-dev ecosystem audit-all`\n'
            "on this package as a normal test. Generated by\n"
            "`scitex-dev ecosystem write-audit-test`. Re-run that command\n"
            "after upgrading scitex-dev to refresh any pin in [dev].\n"
            "\n"
            "Bypass (exceptions / temporal remedy):\n"
            "    SCITEX_DEV_SKIP_AUDIT=1 python -m pytest .\n"
            "\n"
            "Use when remediating pre-existing violations or developing\n"
            "without the audit corpus available locally. CI for release\n"
            "branches MUST NOT set this — drift goes silent.\n"
            '"""\n'
            "\n"
            "import shutil\n"
            "\n"
            "import pytest\n"
            "\n"
            "\n"
            "def test_audit_all_clean():\n"
            '    if shutil.which("scitex-dev") is None:\n'
            "        pytest.skip(\n"
            '            "scitex-dev not installed — add `scitex-dev[cli-audit]` "\n'
            '            "to [project.optional-dependencies.dev]"\n'
            "        )\n"
            "    from scitex_dev.testing import audit_all_for_package\n"
            "\n"
            f"    audit_all_for_package({distribution!r})\n"
        )
        develop_init_content = (
            '"""Dev-hygiene tests — audit conformance, etc.\n'
            "\n"
            "Tests in this directory exercise the package's compliance\n"
            "with ecosystem-wide rules (CLI/MCP/skills/project structure)\n"
            "via `scitex-dev ecosystem audit-all`. They are not unit tests\n"
            "of the package's own logic; those live under tests/<pkg>/.\n"
            '"""\n'
        )
        conftest_content = (
            '"""Pytest fixtures and rootdir marker for this package.\n'
            "\n"
            "An empty conftest.py at tests/ is the canonical SciTeX\n"
            "convention (audit-project PS208) — it pins the pytest\n"
            "rootdir and gives downstream fixtures a home.\n"
            '"""\n'
        )

        # Each entry: (path, content, force_required_to_overwrite).
        # tests/develop/__init__.py and tests/conftest.py are *only*
        # written when missing — they're shared infrastructure, never
        # owned by the audit-test feature. The test_audit.py file IS
        # owned: --force overwrites it on every regeneration.
        plan = [
            (target, test_content, True),
            (develop_init, develop_init_content, False),
            (conftest, conftest_content, False),
        ]

        if dry_run:
            for path, content, _ in plan:
                click.echo(f"# would write: {path}")
                click.echo(content)
                click.echo()
            return

        for path, content, owned in plan:
            if path.exists():
                if owned and not force:
                    click.echo(
                        f"error: {path} already exists (pass --force to overwrite)",
                        err=True,
                    )
                    raise SystemExit(1)
                if not owned:
                    # Don't touch user-owned conftest/__init__ if present.
                    continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            click.echo(f"wrote {path}")

    @ecosystem.command(
        "test-remote",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem test-remote --host bm198 scitex-io\n"
            "  $ scitex-dev ecosystem test-remote --host bm198 --all --audit-only\n"
            "  $ scitex-dev ecosystem test-remote --host bm198 --dry-run scitex-stats\n"
            "\n"
            "rsync local checkouts to HOST, SSH in, install (`pip install -e .[dev]`),\n"
            "run pytest with `-n auto` (xdist when available), stream output, and\n"
            "propagate the exit code. Excludes `.git/`, `__pycache__/`, `*.egg-info/`,\n"
            "`_sphinx_html/`, `GITIGNORED/`, `.scitex/`. With `--all`, fans out across\n"
            "every non-archived ECOSYSTEM package in parallel; failed packages are\n"
            "summarised at the end. Use this to offload heavy parallel runs to a host\n"
            "with spare cores when the local box is loaded."
        ),
    )
    @click.argument("packages", nargs=-1)
    @click.option(
        "--host",
        required=True,
        help="SSH host alias (e.g. `bm198`, `spartan-bm198`). Must be reachable "
        "via `ssh <host>` non-interactively (use ~/.ssh/config).",
    )
    @click.option(
        "--all",
        "all_packages",
        is_flag=True,
        help="Run on every non-archived ECOSYSTEM package (ignores PACKAGES).",
    )
    @click.option(
        "--audit-only",
        is_flag=True,
        help="Only run `tests/develop/test_audit.py`, not the full test tree.",
    )
    @click.option(
        "--jobs",
        "-j",
        type=int,
        default=4,
        show_default=True,
        help="Max packages to run concurrently when --all is set.",
    )
    @click.option(
        "--remote-base",
        default="~/.scitex/dev/test-remote",
        show_default=True,
        help=(
            "Parent directory on HOST where each package is rsynced. "
            "Default is a sandbox under ~/.scitex/ so HOST's own "
            "~/proj/<pkg> working checkouts are never touched."
        ),
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the rsync + ssh commands that would run; don't execute.",
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def ecosystem_test_remote(
        packages, host, all_packages, audit_only, jobs, remote_base, dry_run, yes
    ):
        """Run pytest on HOST against rsynced local checkouts."""
        del yes  # non-destructive on local; remote installs are idempotent
        import shlex
        import subprocess as _sp
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from ..._ecosystem import ECOSYSTEM, get_local_path

        if all_packages:
            targets = [n for n, info in ECOSYSTEM.items() if not info.get("archived")]
        else:
            if not packages:
                click.echo("error: no PACKAGES given (and --all not set)", err=True)
                raise SystemExit(2)
            targets = list(packages)
            for n in targets:
                if n not in ECOSYSTEM:
                    click.echo(f"error: '{n}' not in ECOSYSTEM", err=True)
                    raise SystemExit(2)

        # rsync exclusions — keep payload small and avoid shipping build artefacts
        # that would confuse a fresh install on the remote.
        rsync_excludes = [
            ".git/",
            "__pycache__/",
            "*.egg-info/",
            "_sphinx_html/",
            "GITIGNORED/",
            ".scitex/",
            ".pytest_cache/",
            ".mypy_cache/",
            ".ruff_cache/",
            "build/",
            "dist/",
            "*.pyc",
        ]
        excl_args = []
        for e in rsync_excludes:
            excl_args.extend(["--exclude", e])

        test_path = "tests/develop/" if audit_only else "tests/"

        def _run_one(pkg: str) -> tuple[str, int, str]:
            local = get_local_path(pkg)
            if local is None or not local.exists():
                return pkg, 2, f"local checkout missing: {local}"
            # Per-package layout on HOST. Source and venv live in sibling
            # subtrees so rsync --delete on `src/` never wipes the venv.
            #   <remote_base>/<pkg>/src/     ← rsync target (working tree)
            #   <remote_base>/<pkg>/.venv/   ← persistent per-package venv
            remote_root = f"{remote_base}/{pkg}"
            remote_src = f"{remote_root}/src"
            remote_venv = f"{remote_root}/.venv"
            ssh_mkdir = [
                "ssh",
                host,
                "mkdir",
                "-p",
                shlex.quote(remote_src),
            ]
            rsync_cmd = [
                "rsync",
                "-az",
                "--delete",
                *excl_args,
                f"{local}/",
                f"{host}:{remote_src}/",
            ]
            # Remote one-liner:
            #   1. create the per-package venv if missing,
            #   2. activate it,
            #   3. `pip install -e .[dev]` (with bare-`.` fallback) +
            #      scitex-dev[cli-audit] for the audit gate,
            #   4. pytest -n auto when xdist is available, otherwise serial.
            remote_script = (
                f"set -e; "
                f"if [ ! -f {shlex.quote(remote_venv)}/bin/activate ]; then "
                f"  python3 -m venv {shlex.quote(remote_venv)}; "
                f"fi; "
                f". {shlex.quote(remote_venv)}/bin/activate; "
                f"cd {shlex.quote(remote_src)}; "
                f"python -m pip install --quiet --upgrade pip; "
                f"python -m pip install -e '.[dev]' --quiet || "
                f"python -m pip install -e . --quiet; "
                f"python -m pip install 'scitex-dev[cli-audit]' --quiet; "
                f"python -m pip install pytest-xdist --quiet || true; "
                f"if python -c 'import xdist' 2>/dev/null; then "
                f"  python -m pytest -n auto --tb=short {shlex.quote(test_path)}; "
                f"else "
                f"  python -m pytest --tb=short {shlex.quote(test_path)}; "
                f"fi"
            )
            ssh_cmd = ["ssh", host, "bash", "-lc", shlex.quote(remote_script)]

            if dry_run:
                lines = [
                    "# " + " ".join(shlex.quote(a) for a in ssh_mkdir),
                    "# " + " ".join(shlex.quote(a) for a in rsync_cmd),
                    "# " + " ".join(shlex.quote(a) for a in ssh_cmd),
                ]
                return pkg, 0, "\n".join(lines)

            # mkdir + rsync (sequential — required before ssh)
            for cmd in (ssh_mkdir, rsync_cmd):
                r = _sp.run(cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    return pkg, r.returncode, r.stderr.strip() or r.stdout.strip()
            # pytest run — capture output for the parallel summary
            r = _sp.run(ssh_cmd, capture_output=True, text=True)
            tail = (r.stdout + r.stderr).strip().splitlines()
            tail = "\n".join(tail[-25:]) if len(tail) > 25 else "\n".join(tail)
            return pkg, r.returncode, tail

        if dry_run:
            for pkg in targets:
                _, _, out = _run_one(pkg)
                click.echo(f"--- {pkg} ---")
                click.echo(out)
            return

        click.echo(
            f"# test-remote: host={host}, packages={len(targets)}, "
            f"jobs={jobs}, audit_only={audit_only}"
        )
        results: dict[str, tuple[int, str]] = {}
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            futures = {pool.submit(_run_one, p): p for p in targets}
            for f in as_completed(futures):
                pkg, code, tail = f.result()
                status = "ok" if code == 0 else f"FAIL({code})"
                click.echo(f"[{status:>8}] {pkg}")
                results[pkg] = (code, tail)

        failed = [(p, c, t) for p, (c, t) in results.items() if c != 0]
        click.echo("")
        click.echo(f"# summary: {len(results) - len(failed)} ok, {len(failed)} failed")
        for p, c, t in failed:
            click.echo(f"\n--- {p} (exit {c}) ---")
            click.echo(t)
        raise SystemExit(0 if not failed else 1)

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
    @click.option(
        "--dry-run", is_flag=True, help="Print what would be done; do not start."
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def ecosystem_start_dashboard(
        port, host, debug, no_browser, force, background, dry_run, yes
    ):
        """Launch the ecosystem dashboard web UI.

        \b
        Example:
            $ scitex-dev ecosystem start-dashboard
            $ scitex-dev ecosystem start-dashboard --port 9000 --background
            $ scitex-dev ecosystem start-dashboard --dry-run
        """
        del yes  # accepted for §2; dashboard launch is non-interactive
        if dry_run:
            click.echo(
                f"would launch dashboard on {host}:{port} "
                f"(background={background}, debug={debug}, force={force})"
            )
            return
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
