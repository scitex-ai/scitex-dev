#!/usr/bin/env python3
"""`scitex-dev skills install` (+ hidden deprecated `export` / `collect`)."""

import json

import click
import scitex_logging as slogging

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ....skill_registry import (
    MANIFEST_NAME,
    SCHEMA,
    SkillRegistryError,
    audit_projection,
)
from ._helpers import (
    _default_skills_destination,
    _ensure_symlink,
    _print_export_result,
    _report_symlink,
    _require_external_destination,
    _require_symlink_slot,
)
from ._projection_finalize import (
    install_result_dict,
    registry_from_listing,
)

_logger = slogging.getLogger(__name__)


def register(skills):
    # ----- Canonical: `skills install` (replaces `export` + `collect`) -----
    @skills.command(
        "install",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Install skills from installed/PyPI packages into DEST.",
            description=(
                (
                    "Default DEST is ~/.scitex/dev/skills/ — the canonical "
                    "store. Use --directory to select any agent-readable "
                    "destination; --package limits the owning distribution."
                ),
            ),
            examples=(
                Example(
                    "{prog} dev skills install", "Install to ~/.scitex/dev/skills/."
                ),
                Example(
                    "{prog} dev skills install --directory /tmp/skills --package scitex-writer",
                    "Explicit destination, one package.",
                ),
                Example(
                    "{prog} dev skills install --link",
                    "Editable symlink to source (live edits).",
                ),
                Example(
                    "{prog} dev skills install --dry-run --json", "Preview as JSON."
                ),
            ),
        ),
    )
    @click.option(
        "--directory",
        "--dest",
        "dest",
        type=click.Path(),
        default=None,
        help=(
            "Target directory. Default: ~/.scitex/dev/skills/ — the "
            "canonical store. --dest remains a compatible alias. "
            "Choose a destination readable by your agent or tools."
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
        "--clean",
        is_flag=True,
        help="Refresh requested managed namespaces in the validated staging projection.",
    )
    @click.option(
        "--link",
        is_flag=True,
        help="Symlink skill files to editable source (source=installed only); "
        "edits propagate live with no re-install.",
    )
    @click.option(
        "--no-link",
        is_flag=True,
        help="Copy even when the package is editable; overrides automatic linking.",
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
        dest,
        package,
        source,
        clean,
        link,
        no_link,
        claude_symlink,
        dry_run,
        as_json,
        yes,
    ):
        del yes  # accepted for §2 compliance; install honours --dry-run for preview
        from pathlib import Path

        from ...._ecosystem._skills.skills import list_skills
        from ...._ecosystem._skills.transaction import install_projection

        # DATA/STATE is user-canonical and never project-shadowed.
        target = Path(dest) if dest else _default_skills_destination()
        _require_external_destination(target)
        claude_link = Path.home() / ".claude" / "skills" / "scitex"
        if claude_symlink:
            _require_symlink_slot(claude_link)

        if link and no_link:
            raise click.UsageError("--link and --no-link cannot be combined")
        if dry_run and source == "pypi":
            if as_json:
                click.echo(
                    json.dumps(
                        {
                            "schema_version": SCHEMA,
                            "status": "not-resolved",
                            "ok": False,
                            "discovery_performed": False,
                            "packages": None,
                            "source": "pypi",
                            "requested_package": package,
                            "dry_run": True,
                            "destination": str(target),
                        },
                        indent=2,
                    )
                )
            else:
                click.echo(
                    "PyPI dry-run is unresolved: no wheel metadata was downloaded.",
                    err=True,
                )
            click.get_current_context().exit(2)
        try:
            listed = list_skills(package=package) if source == "installed" else None
        except SkillRegistryError as error:
            if as_json:
                click.echo(
                    json.dumps(
                        {
                            "schema_version": SCHEMA,
                            "ok": False,
                            "status": "refused",
                            "packages": None,
                            "destination": str(target),
                            "findings": [
                                {
                                    "code": "SI-103",
                                    "kind": "invalid",
                                    "name": package or "*",
                                    "path": str(target),
                                    "message": str(error),
                                }
                            ],
                        },
                        indent=2,
                    )
                )
                click.get_current_context().exit(2)
            raise click.ClickException(str(error)) from error
        discovered = (
            registry_from_listing(listed, allow_empty=package is None)
            if listed is not None
            else None
        )
        if discovered is not None and not discovered.ok:
            if as_json:
                click.echo(
                    json.dumps(
                        {
                            "schema_version": SCHEMA,
                            "status": "not-resolved",
                            "ok": False,
                            "discovery_performed": True,
                            "packages": {},
                            "source": source,
                            "dry_run": dry_run,
                            "findings": [
                                issue.to_dict() for issue in discovered.issues
                            ],
                        },
                        indent=2,
                    )
                )
            else:
                click.echo(
                    "Installed skill package discovery is empty or invalid.", err=True
                )
            click.get_current_context().exit(2)
        if dry_run:
            result = {k: [e["name"] + ".md" for e in v] for k, v in listed.items()}
            if as_json:
                click.echo(
                    json.dumps(
                        {
                            "schema_version": SCHEMA,
                            "projection_sha256": None,
                            "manifest": str(target / MANIFEST_NAME),
                            "destination": str(target),
                            "claude_projection": (
                                str(claude_link) if claude_symlink else None
                            ),
                            "packages": result,
                            "findings": [],
                            "ok": True,
                            "dry_run": True,
                            "source": source,
                        },
                        indent=2,
                        sort_keys=True,
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

        finalized, exported = install_projection(
            target,
            package=package,
            clean=clean,
            source=source,
            link=link,
            force_copy=no_link,
        )
        registry = finalized.registry
        extra_findings = ()

        if claude_symlink and finalized.audit.ok:
            claude_link.parent.mkdir(parents=True, exist_ok=True)
            _ensure_symlink(claude_link, target)
            _report_symlink(claude_link, target)
            extra_findings = audit_projection(registry, claude_link).issues

        result = install_result_dict(
            finalized,
            exported,
            target,
            claude_projection=claude_link if claude_symlink else None,
            additional_findings=extra_findings,
        )
        if as_json:
            click.echo(json.dumps(result, indent=2, sort_keys=True))
        elif result["ok"]:
            _print_export_result(exported, target)
        if not result["ok"]:
            for finding in result["findings"]:
                _logger.error(
                    "%s %s %s: %s",
                    finding["code"],
                    finding["kind"],
                    finding["path"],
                    finding["message"],
                )
            raise click.ClickException(
                f"skill projection validation failed with "
                f"{len(result['findings'])} finding(s)"
            )

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

        from ...._ecosystem._skills.skills import (
            _get_default_export_dest,
            export_skills,
        )

        target = Path(dest) if dest else _get_default_export_dest()
        _require_external_destination(target)
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
        _require_external_destination(target)
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
