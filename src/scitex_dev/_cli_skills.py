#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI commands for skills aggregation — registered on main CLI group."""

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
                    click.echo(f"  {s['name']}: {s['description']}")

    @skills.command("get")
    @click.argument("package")
    @click.argument("name")
    def skills_get(package, name):
        """Get content of a specific skill."""
        from .skills import get_skill

        content = get_skill(package=package, name=name)
        if content:
            click.echo(content)
        else:
            click.echo(f"Skill '{name}' not found in package '{package}'.", err=True)
            raise SystemExit(1)
