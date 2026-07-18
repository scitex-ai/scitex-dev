#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``skills`` subcommand group (Click flavor).

Shares its execution path with ``_skills_argparse.py`` -- both dispatch
into ``_skills_list`` / ``_skills_get`` / ``export_skills`` so the
argparse and Click front-ends a downstream package might choose never
drift in behavior.
"""

from __future__ import annotations

import argparse


def skills_click_group(package: str, name: str = "skills"):
    """Create a Click command group for skills (requires Click installed).

    Usage::
        from scitex_dev.cli import skills_click_group
        cli.add_command(skills_click_group(package="scitex-app"))
    """
    try:
        import click
    except ImportError:
        raise ImportError("Click is required. pip install click")

    from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup
    from ._skills_argparse import _skills_get, _skills_list

    @click.group(
        name=name,
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="View package skills (workflow-oriented guides).",
        ),
    )
    @click.pass_context
    def skills_grp(ctx):
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @skills_grp.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List available skill pages.",
            examples=(
                Example("{prog} skills list", "Human-readable list."),
                Example("{prog} skills list --json", "Structured JSON."),
            ),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def skills_list(as_json):
        ns = argparse.Namespace(as_json=as_json)
        _skills_list(ns, package=package)

    @skills_grp.command(
        "get",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Show a specific skill page.",
            examples=(
                Example("{prog} skills get", "List available skills."),
                Example("{prog} skills get python-scitex", "Show one skill."),
                Example(
                    "{prog} skills get python-scitex --json", "Skill as JSON."
                ),
            ),
        ),
    )
    @click.argument("skill_name", required=False, default=None)
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def skills_get(skill_name, as_json):
        if skill_name is None:
            # No name given — show available skills
            ns = argparse.Namespace(as_json=as_json)
            _skills_list(ns, package=package)
            return
        ns = argparse.Namespace(name=skill_name, as_json=as_json)
        _skills_get(ns, package=package)

    @skills_grp.command(
        "export",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Export this package's skills to <dest>.",
            examples=(
                Example("{prog} skills export", "Export to the default dest."),
                Example(
                    "{prog} skills export --dest /tmp/skills",
                    "Export to a custom dest.",
                ),
                Example(
                    "{prog} skills export --dry-run --json",
                    "Preview as structured JSON.",
                ),
            ),
        ),
    )
    @click.option(
        "--dest",
        default=None,
        help="Destination dir (default: ~/.claude/skills/scitex/).",
    )
    @click.option(
        "--source",
        type=click.Choice(["package", "dev", "auto"]),
        default="auto",
        help="Which source to export from.",
    )
    @click.option("--clean", is_flag=True, help="Delete pkg subdir first.")
    @click.option("--dry-run", is_flag=True, help="Preview without writing.")
    @click.option(
        "--yes", "-y", is_flag=True, help="Skip confirmation when overwriting."
    )
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def skills_export(dest, source, clean, dry_run, yes, as_json):
        from pathlib import Path as _P

        from ..._ecosystem._skills.skills import (
            _get_default_export_dest,
            export_skills,
            list_skills,
        )

        target = _P(dest) if dest else _get_default_export_dest()

        if dry_run:
            sl_by_pkg = list_skills(package=package)
            flat = [s for lst in sl_by_pkg.values() for s in lst]
            if as_json:
                import json as _json

                click.echo(
                    _json.dumps({str(target): [s["name"] for s in flat]}, indent=2)
                )
            else:
                click.echo(
                    f"Would export {len(flat)} files for {package} "
                    f"to {target}/ (source={source})"
                )
                for s in flat:
                    click.echo(f"  - {s['name']}")
            return

        exported = export_skills(target, package=package, clean=clean, source=source)
        if not exported:
            click.echo(f"No skills found to export for {package}.")
            return
        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {k: [str(f) for f in v] for k, v in exported.items()},
                    indent=2,
                )
            )
        else:
            total = sum(len(v) for v in exported.values())
            click.echo(f"Exported {total} files for {package} to {target}")

    # `install` is the audit-cli §3 canonical verb name for materialising
    # cached resources to the user's filesystem; we keep `export` as a
    # back-compat alias and bind both to the same callback so existing
    # docs / muscle memory keep working.
    skills_grp.add_command(skills_export, name="install")

    return skills_grp


__all__ = ["skills_click_group"]
