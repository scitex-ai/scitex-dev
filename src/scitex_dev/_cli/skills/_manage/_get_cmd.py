#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev skills get`."""

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(skills):
    @skills.command(
        "get",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary=(
                "Get content of a skill. Use 'all' to dump every skill "
                "across the ecosystem."
            ),
            examples=(
                Example(
                    "{prog} skills get scitex-io save-and-load",
                    "One skill's content.",
                ),
                Example(
                    "{prog} skills get scitex-stats hypothesis-testing --json",
                    "As a JSON envelope.",
                ),
                Example("{prog} skills get all", "Dump every skill."),
            ),
        ),
    )
    @click.argument("package")
    @click.argument("name", required=False, default=None)
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit skill as JSON envelope."
    )
    def skills_get(package, name, as_json):
        from ...._ecosystem._skills.skills import (
            drift_warning,
            get_skill,
            list_skills,
        )

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
            if as_json:
                import json as _json

                click.echo(
                    _json.dumps({"package": package, "name": name, "content": content})
                )
            else:
                click.echo(content)
            # Non-blocking drift signal: cached skill older than installed.
            # Stderr only; never prompts.
            w = drift_warning(package)
            if w:
                click.echo(w, err=True)
        else:
            target = f"'{name}' in " if name else ""
            click.echo(f"Skill {target}package '{package}' not found.", err=True)
            raise SystemExit(1)


__all__ = ["register"]
