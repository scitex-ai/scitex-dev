#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `init-config` — write a `.scitex/dev/config.yaml` from the
heuristic so the user can confirm + commit the project's type."""

import click

from ....._ecosystem.help_spec import CliHelp, Example, SpecCommand

try:
    # SSOT for valid project types; keeps `init-config --project-type`
    # choices in sync with the loader instead of a hand-maintained list.
    from ....audit._config._loader import PROJECT_TYPES as _PROJECT_TYPES

    _PROJECT_TYPE_CHOICES = sorted(_PROJECT_TYPES)
except Exception:  # pragma: no cover - defensive fallback
    _PROJECT_TYPE_CHOICES = ["deferred", "django", "pip", "research", "special"]


def register(ecosystem):
    @ecosystem.command(
        "init-config",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Write .scitex/dev/config.yaml from the heuristic guess.",
            examples=(
                Example("{prog} ecosystem init-config", "Preview + write for cwd."),
                Example(
                    "{prog} ecosystem init-config --project-type research --yes",
                    "Force a project type.",
                ),
                Example(
                    "{prog} ecosystem init-config --project-type pip --project-type research",
                    "Hybrid repo, two types.",
                ),
                Example("{prog} ecosystem init-config --dry-run", "Preview only."),
            ),
        ),
    )
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
        type=click.Choice(_PROJECT_TYPE_CHOICES),
        help=(
            "Override the heuristic guess. Repeatable for hybrid repos "
            "(e.g. a Django app that is also a pip package: "
            "`--project-type pip --project-type django`)."
        ),
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
        del yes  # accepted for §2 compliance; --force gates overwrite
        from pathlib import Path

        from ....audit._config import detect_project_types, write_config

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


__all__ = ["register"]
