#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev skills list`."""

import json

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(skills):
    @skills.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List all skills across installed packages.",
            examples=(
                Example("{prog} skills list", "Every package's skills."),
                Example("{prog} skills list --json", "Structured JSON."),
                Example(
                    "{prog} skills list --package scitex-io",
                    "One package's skills.",
                ),
            ),
        ),
    )
    @click.option("--package", default=None, help="Filter by package name.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def skills_list(package, as_json):
        from ...._ecosystem._skills.skills import drift_warning, list_skills

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
            # Non-blocking drift signal: cached skills older than the
            # installed package version. Stderr only; never prompts.
            for pkg in result:
                w = drift_warning(pkg)
                if w:
                    click.echo(w, err=True)


__all__ = ["register"]
