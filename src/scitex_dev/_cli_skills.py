#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI commands for skills aggregation -- registered on main CLI group."""

import json

import click


def register_skills_commands(main_group):
    """Register skills command group on the main CLI."""

    @main_group.group(invoke_without_command=True)
    @click.pass_context
    def skills(ctx):
        """Manage skills across the SciTeX ecosystem."""
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @skills.command("list")
    @click.option("--package", default=None, help="Filter by package name.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def skills_list(package, as_json):
        """List all skills across installed packages."""
        from .skills import list_skills

        result = list_skills(package=package)
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            if not result:
                click.echo("No skills found.")
                return
            for pkg, items in result.items():
                click.echo(f"\n{pkg}:")
                for s in items:
                    desc = f" -- {s['description']}" if s["description"] else ""
                    click.echo(f"  {s['name']}{desc}")

    @skills.command("get")
    @click.argument("package")
    @click.argument("name", required=False, default=None)
    def skills_get(package, name):
        """Get content of a skill. Without NAME, shows main SKILL.md."""
        from .skills import get_skill

        content = get_skill(package=package, name=name)
        if content:
            click.echo(content)
        else:
            target = f"'{name}' in " if name else ""
            click.echo(f"Skill {target}package '{package}' not found.", err=True)
            raise SystemExit(1)

    @skills.command("export")
    @click.option(
        "--dest",
        type=click.Path(),
        default=None,
        help="Destination directory (default: .claude/skills/).",
    )
    @click.option("--package", default=None, help="Export only this package.")
    @click.option("--clean", is_flag=True, help="Remove destination before exporting.")
    def skills_export(dest, package, clean):
        """Export skills to .claude/skills/ for Claude Code discovery."""
        from pathlib import Path

        from .skills import export_skills

        dest_path = Path(dest) if dest else None
        exported = export_skills(dest=dest_path, package=package, clean=clean)

        if not exported:
            click.echo("No skills found to export.")
            return

        total = 0
        for pkg_name, files in sorted(exported.items()):
            click.echo(f"  {pkg_name}/")
            for f in files:
                click.echo(f"    {f}")
                total += 1

        target = dest_path or Path(".claude/skills/")
        click.echo(f"\nExported {total} files to {target}")
