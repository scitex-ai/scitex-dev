"""``hooks install`` and ``hooks update`` leaves.

Both materialise a SYMLINK at ``<project>/<deploy_rel>`` pointing at the
bundled hook script inside the installed scitex-dev package. ``update``
is just ``install --force`` restricted to projects that already have the
directory tree.
"""

from __future__ import annotations

from pathlib import Path

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ._registry import KNOWN_HOOKS, _install_one, install_symbol


def register_install(hooks_group) -> None:
    """Attach the ``install`` and ``update`` leaves to ``hooks_group``."""

    @hooks_group.command(
        "install",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Install bundled hooks as symlinks into the target project.",
            examples=(
                Example(
                    "{prog} hooks install --target ~/proj/my-research",
                    "installed run_lint -> .../docs/to_claude/hooks/post-tool-use/run_lint.sh",
                ),
            ),
        ),
    )
    @click.option(
        "--target",
        "target",
        required=True,
        type=click.Path(file_okay=False, dir_okay=True, exists=False, resolve_path=True),
        help="Project root to install hooks into (created if missing).",
    )
    @click.option(
        "--name",
        "names",
        multiple=True,
        type=click.Choice(sorted(KNOWN_HOOKS), case_sensitive=False),
        help=(
            "Limit installation to specific hook names. Defaults to all "
            "known hooks."
        ),
    )
    @click.option(
        "--force",
        is_flag=True,
        help=(
            "Overwrite an existing non-symlink file at the deploy path. "
            "By default a real file blocks installation so an operator "
            "edit is never silently clobbered."
        ),
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help=(
            "Print what would change without touching the filesystem. "
            "audit-cli §2 — every mutating verb must expose --dry-run."
        ),
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        help=(
            "Accept all confirmation prompts (no-op today; symlink installs "
            "are non-interactive). Required by audit-cli §2 for mutating "
            "verbs so callers can scriptedly bypass any future confirm "
            "logic."
        ),
    )
    def hooks_install(target, names, force, dry_run, yes):
        del yes  # --yes is reserved for audit-cli §2 conformance; no
                 # confirmation prompts are issued today.
        project = Path(target)
        if not dry_run:
            project.mkdir(parents=True, exist_ok=True)
        chosen = list(names) if names else sorted(KNOWN_HOOKS)
        had_refusal = False
        for name in chosen:
            source, deploy_rel = KNOWN_HOOKS[name]
            if dry_run:
                target_path = project / deploy_rel
                click.echo(f"would install  {name}  →  {target_path}")
                continue
            status = _install_one(name, source, deploy_rel, project, force)
            target_path = project / deploy_rel
            click.echo(f"{install_symbol(status)}  {name}  →  {target_path}")
            if status == "refused":
                had_refusal = True
                click.echo(
                    click.style(
                        "  (a non-symlink file exists at the target; pass "
                        "--force to overwrite, or remove it manually.)",
                        fg="red",
                    ),
                    err=True,
                )
        if had_refusal:
            raise SystemExit(1)

    @hooks_group.command(
        "update",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Re-link installed hooks to the current canonical.",
            description=(
                "Equivalent to `install --force` for a project that "
                "already has the directory tree. Replaces non-symlink "
                "files too — call only when you mean to discard local "
                "edits.",
            ),
            examples=(
                Example(
                    "{prog} hooks update --target ~/proj/my-research",
                    "Re-link to the current canonical hooks.",
                ),
            ),
        ),
    )
    @click.option(
        "--target",
        "target",
        required=True,
        type=click.Path(file_okay=False, dir_okay=True, exists=True, resolve_path=True),
        help="Project root with an existing hooks directory.",
    )
    @click.option(
        "--name",
        "names",
        multiple=True,
        type=click.Choice(sorted(KNOWN_HOOKS), case_sensitive=False),
        help="Limit update to specific hook names. Defaults to all.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help=(
            "Print what would change without touching the filesystem. "
            "audit-cli §2 — every mutating verb must expose --dry-run."
        ),
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        help=(
            "Accept all confirmation prompts (no-op today; no interactive "
            "confirm logic). Required by audit-cli §2 for mutating verbs."
        ),
    )
    def hooks_update(target, names, dry_run, yes):
        del yes
        project = Path(target)
        chosen = list(names) if names else sorted(KNOWN_HOOKS)
        for name in chosen:
            source, deploy_rel = KNOWN_HOOKS[name]
            if dry_run:
                click.echo(f"would update  {name}  →  {project / deploy_rel}")
                continue
            status = _install_one(name, source, deploy_rel, project, force=True)
            click.echo(f"{install_symbol(status)}  {name}  →  {project / deploy_rel}")


__all__ = ["register_install"]
