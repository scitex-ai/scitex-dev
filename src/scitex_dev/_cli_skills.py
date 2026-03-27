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
        """Get content of a skill. Use 'all' to dump every skill across the ecosystem."""
        from .skills import get_skill, list_skills

        if package == "all":
            all_skills = list_skills()
            if not all_skills:
                click.echo("No skills found.", err=True)
                raise SystemExit(1)
            for pkg_name, entries in sorted(all_skills.items()):
                for entry in entries:
                    content = get_skill(
                        package=pkg_name,
                        name=entry["name"] if entry["name"] != "SKILL" else None,
                    )
                    if content:
                        click.echo(f"\n{'=' * 60}")
                        click.echo(f"# {pkg_name}/{entry['name']}")
                        click.echo(f"{'=' * 60}\n")
                        click.echo(content)
            return

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
        help="Exact target directory (default: ~/.claude/skills/scitex/).",
    )
    @click.option("--package", default=None, help="Export only this package.")
    @click.option(
        "--source",
        type=click.Choice(["installed", "pypi"]),
        default="installed",
        help="installed or pypi.",
    )
    @click.option(
        "--clean", is_flag=True, help="Delete package subdirs before exporting."
    )
    @click.option("--dry-run", is_flag=True, help="Preview without copying.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def skills_export(dest, package, source, clean, dry_run, as_json):
        """Export skills to ~/.claude/skills/scitex/."""
        import json as json_mod
        from pathlib import Path
        from .skills import _get_default_export_dest, export_skills

        target = Path(dest) if dest else _get_default_export_dest()
        if dry_run:
            from .skills import list_skills

            result = {
                k: [e["name"] + ".md" for e in v]
                for k, v in list_skills(package=package).items()
            }
            if as_json:
                click.echo(
                    json_mod.dumps(
                        {"dest": str(target), "source": source, "packages": result},
                        indent=2,
                    )
                )
            else:
                total = sum(len(v) for v in result.values())
                click.echo(f"Would export {total} files to {target}/ (source={source})")
                for k, v in sorted(result.items()):
                    click.echo(f"  {k}/: {len(v)} files")
            return
        exported = export_skills(target, package=package, clean=clean, source=source)
        _print_export_result(exported, target, as_json)


def _print_export_result(exported, dest_path, as_json=False):
    """Print export results."""
    import json as json_mod

    if not exported:
        click.echo("No skills found to export.")
        return
    if as_json:
        click.echo(
            json_mod.dumps(
                {k: [str(f) for f in v] for k, v in exported.items()}, indent=2
            )
        )
    else:
        total = sum(len(v) for v in exported.values())
        click.echo(
            f"Exported {total} files across {len(exported)} packages to {dest_path}"
        )
        for k, v in sorted(exported.items()):
            click.echo(f"  {k}: {len(v)} files")
