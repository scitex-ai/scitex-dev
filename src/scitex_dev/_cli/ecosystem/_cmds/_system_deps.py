#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem ``system-deps`` -- aggregate every leaf's declared apt deps.

Each scitex leaf declares its SYSTEM (apt) packages via a
``scitex_dev.system_deps`` entry-point provider; this command aggregates them
(deduped by package) so container builds install ONE federated set instead of
hardcoding/duplicating apt lists across container definitions.

apt needs root, so ``--install`` is BUILD-TIME only (run in a container
``%post`` / Dockerfile). ``--list`` emits apt names for piping, e.g.::

    apt-get install -y --no-install-recommends \\
        $(scitex-dev ecosystem system-deps --list)
"""

from __future__ import annotations

import click


def _select(provider):
    """Discover + optionally filter to one provider."""
    from ....system_deps import discover_system_deps

    deps = discover_system_deps()
    if provider:
        deps = [d for d in deps if d.provider == provider]
    return deps


def _do_install(deps, *, dry_run: bool) -> int:
    """apt-get install the aggregated set (BUILD-time; needs root).

    ``dry_run`` previews the exact apt commands without running them; it is the
    default when ``--yes`` is omitted (§2 mutating-verb convention).
    """
    import os
    import subprocess

    if not deps:
        click.echo("No system deps declared by any provider; nothing to install.")
        return 0

    repos = sorted({d.apt_repo for d in deps if d.apt_repo})
    packages = [d.package for d in deps]

    if dry_run:
        for repo in repos:
            click.echo(f"+ add-apt-repository -y {repo}")
        click.echo("+ apt-get update")
        click.echo(f"+ apt-get install -y --no-install-recommends {' '.join(packages)}")
        click.echo("(dry-run — pass --yes to execute; BUILD-time / root only)")
        return 0

    if hasattr(os, "geteuid") and os.geteuid() != 0:
        click.echo(
            "ERROR: install --yes needs root and runs at IMAGE-BUILD time only "
            "(agents are rootless --userns). Use it inside a container %post / "
            "Dockerfile, or pipe `system-deps list` into apt-get there.",
            err=True,
        )
        return 1

    for repo in repos:
        click.echo(f"+ add-apt-repository -y {repo}")
        if subprocess.run(["add-apt-repository", "-y", repo]).returncode != 0:
            click.echo(f"ERROR: add-apt-repository failed for {repo}", err=True)
            return 1
    if subprocess.run(["apt-get", "update"]).returncode != 0:
        click.echo("ERROR: apt-get update failed", err=True)
        return 1
    click.echo(f"+ apt-get install -y --no-install-recommends {' '.join(packages)}")
    rc = subprocess.run(
        ["apt-get", "install", "-y", "--no-install-recommends", *packages]
    ).returncode
    if rc != 0:
        click.echo("ERROR: apt-get install failed", err=True)
        return 1
    return 0


def _render(deps) -> None:
    """Human-readable table of the aggregated declarations."""
    from rich.console import Console
    from rich.table import Table

    if not deps:
        Console().print("[yellow]No system deps declared by any provider.[/yellow]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("package")
    table.add_column("provider")
    table.add_column("purpose")
    table.add_column("apt_repo")
    for dep in deps:
        table.add_row(dep.package, dep.provider, dep.purpose, dep.apt_repo or "-")
    Console().print(table)
    Console().print(
        f"[bold]{len(deps)}[/bold] system package(s) across "
        f"{len({d.provider for d in deps})} provider(s)."
    )


def _emit_json(deps) -> None:
    import json as _json

    click.echo(
        _json.dumps(
            [
                {
                    "package": d.package,
                    "purpose": d.purpose,
                    "provider": d.provider,
                    "apt_repo": d.apt_repo,
                }
                for d in deps
            ],
            indent=2,
        )
    )


def register(ecosystem):
    @ecosystem.group(
        "system-deps",
        invoke_without_command=True,
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem system-deps               # table\n"
            "  $ scitex-dev ecosystem system-deps list          # apt names, one/line\n"
            "  $ apt-get install -y --no-install-recommends \\\n"
            "        $(scitex-dev ecosystem system-deps list)\n"
            "  $ scitex-dev ecosystem system-deps install       # BUILD-time, root\n"
            "  $ scitex-dev ecosystem system-deps list --provider scitex-writer\n"
            "\n"
            "Declarations live in each leaf (scitex_dev.system_deps entry point);\n"
            "this aggregates + dedups by apt package. INSTALL IS BUILD-TIME ONLY\n"
            "(apt needs root; agents run rootless --userns)."
        ),
    )
    @click.pass_context
    def system_deps(ctx):
        """Aggregate the ecosystem's declared system (apt) dependencies.

        Walks every ``scitex_dev.system_deps`` provider and dedups by apt
        package name. With no subcommand, prints a human table; ``list`` is
        pipe-friendly; ``install`` applies them at image-build time.
        """
        if ctx.invoked_subcommand is None:
            _render(_select(None))

    @system_deps.command(
        "list",
        epilog=(
            "Example:\n"
            "  $ scitex-dev ecosystem system-deps list\n"
            "  $ apt-get install -y --no-install-recommends \\\n"
            "        $(scitex-dev ecosystem system-deps list)"
        ),
    )
    @click.option(
        "--provider",
        default=None,
        help="Filter to one declaring package (e.g. scitex-writer).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
    def system_deps_list(provider, as_json):
        """Print the aggregated apt package names, one per line (pipe-friendly).

        \b
        Example:
            $ scitex-dev ecosystem system-deps list
            $ apt-get install -y $(scitex-dev ecosystem system-deps list)
        """
        deps = _select(provider)
        if as_json:
            _emit_json(deps)
            return 0
        for dep in deps:
            click.echo(dep.package)
        return 0

    @system_deps.command(
        "install",
        epilog=(
            "Example:\n"
            "  $ scitex-dev ecosystem system-deps install        # preview\n"
            "  $ scitex-dev ecosystem system-deps install --yes  # execute (root)"
        ),
    )
    @click.option(
        "--provider",
        default=None,
        help="Filter to one declaring package (e.g. scitex-writer).",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the apt commands without running them (default when --yes "
        "is omitted).",
    )
    @click.option(
        "--yes",
        "-y",
        "yes",
        is_flag=True,
        help="Actually run apt-get (BUILD-time; needs root).",
    )
    def system_deps_install(provider, dry_run, yes):
        """apt-get install the aggregated set (BUILD-time; needs root).

        Mutating verb: previews (dry-run) unless --yes is given.

        \b
        Example:
            $ scitex-dev ecosystem system-deps install        # preview
            $ scitex-dev ecosystem system-deps install --yes  # execute (root)
        """
        return _do_install(_select(provider), dry_run=dry_run or not yes)
