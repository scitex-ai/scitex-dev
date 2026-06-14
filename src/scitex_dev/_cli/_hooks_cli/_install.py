"""``hooks install`` and ``hooks update`` subcommands.

Both materialise a SYMLINK at ``<project>/<deploy_rel>`` pointing at
the bundled hook script inside the installed scitex-dev package.
``update`` is just ``install --force`` restricted to projects that
already have the hook directory tree (the click ``--target`` option
requires ``exists=True`` for ``update``).
"""

from __future__ import annotations

from pathlib import Path

import click

from ._registry import KNOWN_HOOKS, install_one


def _status_style(status: str) -> str:
    return {
        "installed": click.style("installed ", fg="green"),
        "updated": click.style("updated   ", fg="green"),
        "up-to-date": click.style("up-to-date", fg="cyan"),
        "refused": click.style("refused   ", fg="red"),
        "forced": click.style("forced    ", fg="yellow"),
    }.get(status, status)


def register(hooks_group) -> None:
    """Attach the ``install`` and ``update`` leaves to ``hooks_group``."""

    @hooks_group.command(
        "install", short_help="Install canonical hooks into a project."
    )
    @click.option(
        "--target",
        "target",
        required=True,
        type=click.Path(
            file_okay=False, dir_okay=True, exists=False, resolve_path=True
        ),
        help="Project root to install hooks into (created if missing).",
    )
    @click.option(
        "--name",
        "names",
        multiple=True,
        type=click.Choice(sorted(KNOWN_HOOKS), case_sensitive=False),
        help=(
            "Limit installation to specific hook names. Defaults to all known hooks."
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
        """Install bundled hooks as symlinks into the target project.

        \b
        Example:
            $ scitex-dev hooks install --target ~/proj/my-research
            installed  run_lint  →  ~/proj/my-research/docs/to_claude/hooks/post-tool-use/run_lint.sh
        """
        del yes  # reserved for audit-cli §2 conformance; no confirmation prompts today.
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
            status = install_one(name, source, deploy_rel, project, force)
            target_path = project / deploy_rel
            click.echo(f"{_status_style(status)}  {name}  →  {target_path}")
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
        "update", short_help="Re-link installed hooks to the current canonical."
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
        """Equivalent to ``install --force`` for a project that already
        has the directory tree. Replaces non-symlink files too — call
        only when you mean to discard local edits.

        \b
        Example:
            $ scitex-dev hooks update --target ~/proj/my-research
        """
        del yes
        project = Path(target)
        chosen = list(names) if names else sorted(KNOWN_HOOKS)
        for name in chosen:
            source, deploy_rel = KNOWN_HOOKS[name]
            if dry_run:
                click.echo(f"would update  {name}  →  {project / deploy_rel}")
                continue
            status = install_one(name, source, deploy_rel, project, force=True)
            click.echo(f"{_status_style(status)}  {name}  →  {project / deploy_rel}")


__all__ = ["register"]
