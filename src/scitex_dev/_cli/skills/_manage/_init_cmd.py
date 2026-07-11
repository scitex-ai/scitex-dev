#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev skills init`."""

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(skills):
    @skills.command(
        "init",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Scaffold a `_skills/<pip-name>/` tree per the standard template.",
            examples=(
                Example(
                    "{prog} skills init --package my-package",
                    "Scaffold the default set.",
                ),
                Example(
                    "{prog} skills init --package scitex-foo --with-mcp --with-http",
                    "Include MCP + HTTP reference pages.",
                ),
                Example(
                    "{prog} skills init --package my-package --dest /tmp/skills/ --dry-run",
                    "Preview to a custom dest.",
                ),
            ),
        ),
    )
    @click.option(
        "--package",
        "pip_name",
        required=True,
        help="pip distribution name (e.g. `my-package`).",
    )
    @click.option(
        "--import-name",
        default=None,
        help="Python import name (default: pip-name with `-` → `_`).",
    )
    @click.option(
        "--dest",
        type=click.Path(),
        default=None,
        help="Target directory (default: src/<import>/_skills/<pip-name>/).",
    )
    @click.option(
        "--with-cli/--no-cli", default=True, help="Include 04_cli-reference.md."
    )
    @click.option("--with-mcp/--no-mcp", default=False, help="Include 05_mcp-tools.md.")
    @click.option(
        "--with-http/--no-http", default=False, help="Include 06_http-api.md."
    )
    @click.option("--with-env/--no-env", default=True, help="Include 20_env-vars.md.")
    @click.option("--force", is_flag=True, help="Overwrite existing files.")
    @click.option("--dry-run", is_flag=True, help="Preview without writing.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def skills_init(
        pip_name,
        import_name,
        dest,
        with_cli,
        with_mcp,
        with_http,
        with_env,
        force,
        dry_run,
        as_json,
        yes,
    ):
        del yes  # accepted for §2 compliance; init honours --dry-run for preview
        import json as _json
        from pathlib import Path

        from ...._ecosystem._skills._scaffold import (
            build_plan,
            scaffold_package_skills,
        )

        imp = import_name or pip_name.replace("-", "_")
        target = Path(dest) if dest else Path("src") / imp / "_skills" / pip_name
        plan = build_plan(
            pip_name=pip_name,
            import_name=imp,
            dest=target,
            with_cli=with_cli,
            with_mcp=with_mcp,
            with_http=with_http,
            with_env=with_env,
        )

        if dry_run:
            payload = {
                "dest": str(plan.dest),
                "files": sorted(plan.files.keys()),
            }
            if as_json:
                click.echo(_json.dumps(payload, indent=2))
            else:
                click.echo(f"Would scaffold {len(plan.files)} files at {plan.dest}/")
                for name in payload["files"]:
                    click.echo(f"  {name}")
            return

        written, skipped = scaffold_package_skills(plan, force=force)
        if as_json:
            click.echo(
                _json.dumps(
                    {
                        "dest": str(plan.dest),
                        "written": [str(p) for p in written],
                        "skipped": [str(p) for p in skipped],
                    },
                    indent=2,
                )
            )
        else:
            click.echo(
                f"Scaffolded {len(written)} files at {plan.dest}/"
                + (
                    f" ({len(skipped)} skipped — use --force to overwrite)"
                    if skipped
                    else ""
                )
            )
            for p in written:
                click.echo(f"  + {p.name}")
            for p in skipped:
                click.echo(f"  . {p.name} (exists)")


__all__ = ["register"]
