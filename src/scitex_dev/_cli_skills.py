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
                version = items[0].get("version", "") if items else ""
                ver_str = f" (v{version})" if version and version != "unknown" else ""
                click.echo(f"\n{pkg}{ver_str}:")
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
        help="Destination directory (default: .claude/skills/scitex/).",
    )
    @click.option("--package", default=None, help="Export only this package.")
    @click.option("--dry-run", is_flag=True, help="Preview without copying.")
    def skills_export(dest, package, dry_run):
        """Export skills to .claude/skills/scitex/ for Claude Code discovery."""
        from pathlib import Path

        from .skills import export_skills

        dest_path = Path(dest) if dest else None
        if dry_run:
            from .skills import list_skills, _get_default_export_dest

            target = dest_path or _get_default_export_dest()
            if target.name != "scitex":
                target = target / "scitex"
            all_skills = list_skills(package=package)
            for pkg_name, entries in sorted(all_skills.items()):
                click.echo(f"  {pkg_name}/")
                for e in entries:
                    click.echo(
                        f"    {e['name']}.md -> {target / pkg_name / (e['name'] + '.md')}"
                    )
            return
        exported = export_skills(dest=dest_path, package=package, mode="export")
        _print_export_result(exported, dest_path)

    @skills.command("update")
    @click.option(
        "--dest",
        type=click.Path(),
        default=None,
        help="Destination directory.",
    )
    @click.option("--package", default=None, help="Update only this package.")
    def skills_update(dest, package):
        """Update skills (rsync-like, preserves local changes)."""
        from pathlib import Path

        from .skills import export_skills

        dest_path = Path(dest) if dest else None
        exported = export_skills(dest=dest_path, package=package, mode="update")
        _print_export_result(exported, dest_path)

    @skills.command("upgrade")
    @click.option(
        "--dest",
        type=click.Path(),
        default=None,
        help="Destination directory.",
    )
    @click.option("--package", default=None, help="Upgrade only this package.")
    def skills_upgrade(dest, package):
        """Upgrade skills (clean replacement, removes local changes)."""
        from pathlib import Path

        from .skills import export_skills

        dest_path = Path(dest) if dest else None
        exported = export_skills(dest=dest_path, package=package, mode="upgrade")
        _print_export_result(exported, dest_path)


def _print_export_result(exported, dest_path):
    """Print export/update/upgrade results."""
    from pathlib import Path

    from .skills import _get_default_export_dest

    if not exported:
        click.echo("No skills found to export.")
        return

    total = 0
    for pkg_name, files in sorted(exported.items()):
        click.echo(f"  {pkg_name}/")
        for f in files:
            click.echo(f"    {Path(f).name}")
            total += 1

    target = dest_path or _get_default_export_dest()
    click.echo(f"\nExported {total} files to {target}")
