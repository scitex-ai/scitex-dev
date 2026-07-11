#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev skills install` (+ hidden deprecated `export` / `collect`)."""

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ._helpers import _print_export_result


def register(skills):
    # ----- Canonical: `skills install` (replaces `export` + `collect`) -----
    @skills.command(
        "install",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Install skills from installed/PyPI packages into DEST.",
            description=(
                "Default DEST is ~/.scitex/dev/skills/ — the canonical "
                "store, peer to ~/.scitex/{audio,browser,scholar,...}/. "
                "Pass --claude-symlink to also expose the store under "
                "~/.claude/skills/scitex/.",
            ),
            examples=(
                Example(
                    "{prog} skills install", "Install to ~/.scitex/dev/skills/."
                ),
                Example(
                    "{prog} skills install --claude-symlink",
                    "Also expose under ~/.claude/skills/scitex/.",
                ),
                Example(
                    "{prog} skills install --dest /tmp/skills --package scitex-writer",
                    "Custom dest, one package.",
                ),
                Example(
                    "{prog} skills install --link",
                    "Editable symlink to source (live edits).",
                ),
                Example(
                    "{prog} skills install --dry-run --json", "Preview as JSON."
                ),
            ),
        ),
    )
    @click.option(
        "--dest",
        type=click.Path(),
        default=None,
        help=(
            "Target directory. Default: ~/.scitex/dev/skills/ — the "
            "canonical store, peer to ~/.scitex/{audio,browser,scholar,...}/. "
            "Use --claude-symlink to also expose under ~/.claude/skills/scitex/."
        ),
    )
    @click.option("--package", default=None, help="Install only this package.")
    @click.option(
        "--source",
        type=click.Choice(["installed", "pypi"]),
        default="installed",
        help="installed or pypi.",
    )
    @click.option(
        "--clean", is_flag=True, help="Delete package subdirs before installing."
    )
    @click.option(
        "--link",
        is_flag=True,
        help="Symlink skill files to editable source (source=installed only); "
        "edits propagate live with no re-install.",
    )
    @click.option(
        "--claude-symlink",
        is_flag=True,
        help="After install, ensure ~/.claude/skills/scitex → DEST (idempotent). "
        "For Claude Code consumers; does not affect the source of truth at DEST.",
    )
    @click.option("--dry-run", is_flag=True, help="Preview without copying.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def skills_install(
        dest, package, source, clean, link, claude_symlink, dry_run, as_json, yes
    ):
        del yes  # accepted for §2 compliance; install honours --dry-run for preview
        import json as json_mod
        import os as _os
        from pathlib import Path

        from ...._ecosystem._skills.skills import export_skills, list_skills

        # Default to ~/.scitex/dev/skills/ (peer to other ~/.scitex/<pkg>/ stores)
        target = Path(dest) if dest else Path.home() / ".scitex" / "dev" / "skills"

        if dry_run:
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
                click.echo(
                    f"Would install {total} files to {target}/ (source={source})"
                )
                for k, v in sorted(result.items()):
                    click.echo(f"  {k}/: {len(v)} files")
                if claude_symlink:
                    claude_link = Path.home() / ".claude" / "skills" / "scitex"
                    click.echo(f"Would symlink {claude_link} → {target}")
            return

        target.mkdir(parents=True, exist_ok=True)
        exported = export_skills(
            target, package=package, clean=clean, source=source, link=link
        )

        if claude_symlink:
            claude_link = Path.home() / ".claude" / "skills" / "scitex"
            claude_link.parent.mkdir(parents=True, exist_ok=True)
            # Idempotent: replace stale link, leave non-link contents alone.
            if claude_link.is_symlink() or not claude_link.exists():
                if claude_link.is_symlink():
                    claude_link.unlink()
                _os.symlink(target.resolve(), claude_link)
                click.echo(f"linked: {claude_link} → {target}")
            else:
                click.echo(
                    f"warning: {claude_link} exists and is not a symlink — "
                    "skipping --claude-symlink (move it aside manually if needed).",
                    err=True,
                )

        _print_export_result(exported, target, as_json)

    # ----- Deprecated `export` — same behaviour, default destination differs -----
    @skills.command("export", hidden=True)
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
    @click.option(
        "--link",
        is_flag=True,
        help="Symlink skill files to editable source (source=installed only); "
        "edits propagate live with no re-export.",
    )
    @click.option("--dry-run", is_flag=True, help="Preview without copying.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def skills_export(dest, package, source, clean, link, dry_run, as_json):
        """Export skills to ~/.claude/skills/scitex/."""
        import json as json_mod
        from pathlib import Path

        from ...._ecosystem._skills.skills import _get_default_export_dest, export_skills

        target = Path(dest) if dest else _get_default_export_dest()
        if dry_run:
            from ...._ecosystem._skills.skills import list_skills

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
        exported = export_skills(
            target, package=package, clean=clean, source=source, link=link
        )
        _print_export_result(exported, target, as_json)

    @skills.command("collect", hidden=True)
    @click.argument(
        "destination",
        type=click.Path(),
    )
    @click.option("--package", default=None, help="Collect only this package.")
    @click.option(
        "--source",
        type=click.Choice(["installed", "pypi"]),
        default="installed",
        help="Source of skill files (default: installed packages).",
    )
    @click.option(
        "--clean",
        is_flag=True,
        help="Delete package subdirs at destination before collecting.",
    )
    @click.option(
        "--link",
        is_flag=True,
        help="Symlink skill files to editable source (source=installed only).",
    )
    @click.option("--dry-run", is_flag=True, help="Preview without copying.")
    @click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
    def skills_collect(destination, package, source, clean, link, dry_run, as_json):
        """Collect skills from installed/PyPI packages into DESTINATION.

        Unlike `export` (which defaults to ~/.claude/skills/scitex/), this
        command REQUIRES the destination argument so callers always know
        exactly where skills will land.

        \b
        Examples:
          scitex-dev skills collect .claude/skills/scitex/
          scitex-dev skills collect ~/.claude/skills/scitex/
          scitex-dev skills collect docs/to_claude/skills/scitex/
          scitex-dev skills collect /some/path --package scitex-writer
        """
        import json as json_mod
        from pathlib import Path

        from ...._ecosystem._skills.skills import export_skills, list_skills

        target = Path(destination)
        if dry_run:
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
                click.echo(
                    f"Would collect {total} files to {target}/ (source={source})"
                )
                for k, v in sorted(result.items()):
                    click.echo(f"  {k}/: {len(v)} files")
            return
        collected = export_skills(
            target, package=package, clean=clean, source=source, link=link
        )
        _print_export_result(collected, target, as_json)


__all__ = ["register"]
