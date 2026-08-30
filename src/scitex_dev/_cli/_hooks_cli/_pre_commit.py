#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``hooks enable-pre-commit`` — refuse commits on local ``main``.

Sibling of ``enable-pre-push`` and deliberately built the same way: the
symlink AND the ``core.hooksPath`` wiring in one step, sharing
:mod:`._hookspath` so the two leaves cannot disagree about what "already
set" means. Installing only the symlink leaves a guard that is present,
readable, executable and never runs — and a guard that cannot fire is
worse than none, because its absence would at least be visible.

WHAT IT GUARDS, AND WHY A CONVENTION WAS NOT ENOUGH
---------------------------------------------------
Local ``main`` is a READ-ONLY MIRROR of ``origin/main``; its only
legitimate operation is ``pull``. Measured 2026-08-30, ``main`` was
ahead of ``develop`` in every repository checked, because real feature
PRs had been merged with ``main`` as their base — a fleet-wide licence
fix landed on three repositories' main and none of their develops, and
three release PRs had been CONFLICTED for weeks as a result.

WHAT IT CANNOT BREAK — the release. A release TAGS and PUSHES; the merge
of develop into main happens on the REMOTE through a pull request.
``scitex_dev._release.publisher`` contains no ``git commit`` at all, and
already runs its pushes under ``-c core.hooksPath=/dev/null``. A
pre-commit hook has nothing to fire on there.
"""

from __future__ import annotations

from pathlib import Path

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ._hookspath import (
    CONFIGURED,
    FAILED,
    FORCED,
    HOOKS_DIR,
    NO_GIT,
    REFUSED,
    WIRED,
    plan_hookspath,
    read_hookspath,
    wire_hookspath,
)
from ._registry import KNOWN_HOOKS, _install_one, install_symbol

_ROAD = (
    "local develop -> topic branch -> push -> PR to origin/develop -> "
    "pull to local develop -> tag, push to origin/develop -> origin/main; "
    "publish -> pull to local main"
)


def _report_wiring(project: Path, wired: str, previous: str, detail: str) -> None:
    """Print the outcome of the ``core.hooksPath`` step, or exit."""
    if wired == NO_GIT:
        click.echo(
            click.style(
                "error: `git` binary not found on PATH; cannot wire "
                "core.hooksPath. Install git and re-run.",
                fg="red",
            ),
            err=True,
        )
        raise SystemExit(1)
    if wired == WIRED:
        click.echo(
            click.style(
                f"up-to-date  core.hooksPath = {HOOKS_DIR} (already wired)",
                fg="cyan",
            )
        )
        return
    if wired == REFUSED:
        click.echo(
            click.style(
                f"refused    core.hooksPath already set to {previous!r}; "
                f"refusing to overwrite without --force",
                fg="red",
            ),
            err=True,
        )
        click.echo(
            click.style(
                f"    git -C {project} config --unset core.hooksPath",
                fg="red",
            ),
            err=True,
        )
        raise SystemExit(1)
    if wired == FAILED:
        click.echo(
            click.style(
                f"error: `git config core.hooksPath` failed: {detail}", fg="red"
            ),
            err=True,
        )
        raise SystemExit(1)
    if wired == FORCED:
        click.echo(
            click.style("forced    ", fg="yellow")
            + f"  core.hooksPath = {HOOKS_DIR} (forced; was: {previous!r})"
        )
        return
    click.echo(
        click.style("configured", fg="green")
        + f"  core.hooksPath = {HOOKS_DIR} (was: unset — git default)"
    )


def register_pre_commit(hooks_group) -> None:
    """Attach the ``enable-pre-commit`` leaf to ``hooks_group``."""

    @hooks_group.command(
        "enable-pre-commit",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Refuse commits on local main/master AND wire core.hooksPath.",
            description=(
                "Local `main` is a READ-ONLY MIRROR of origin/main: its "
                "only legitimate operation is `pull`. This installs the "
                "guard that enforces that, in two steps so nobody ships a "
                "half-installed hook that silently no-ops: (1) symlinks "
                "the bundled `pre-commit.sh` into "
                "`<target>/.githooks/pre-commit`, and (2) runs `git -C "
                "<target> config core.hooksPath .githooks` — without step "
                "2 git never looks there. The refusal message NAMES THE "
                "ROAD rather than only saying no: " + _ROAD + ". It does "
                "NOT affect the release path, which tags and pushes and "
                "never commits, and merges develop into main on the REMOTE "
                "through a PR. core.hooksPath is ADDITIVE-then-refuse: "
                "unset -> set; already .githooks -> no-op; anything else "
                "-> REFUSE unless --force. Escape hatches stay open and "
                "loud: `SCITEX_DEV_ALLOW_MAIN_COMMIT=1 git commit` or `git "
                "commit --no-verify`."
            ),
            examples=(
                Example(
                    "{prog} dev hooks enable-pre-commit --target ~/proj/scitex-io",
                    "installed pre_commit -> .githooks/pre-commit; configured core.hooksPath.",
                ),
                Example(
                    "{prog} dev hooks enable-pre-commit --target . --dry-run",
                    "Plan the symlink + git-config actions without touching anything.",
                ),
            ),
        ),
    )
    @click.option(
        "--target",
        "target",
        required=True,
        type=click.Path(file_okay=False, dir_okay=True, exists=True, resolve_path=True),
        help="Repo root to install the main-branch commit guard into.",
    )
    @click.option(
        "--force",
        is_flag=True,
        help=(
            "Overwrite an existing non-symlink `.githooks/pre-commit`, or a "
            "`core.hooksPath` pointing anywhere other than `.githooks`. "
            "Both are refused by default so an operator's own hooks are "
            "never silently clobbered; the prior values are printed."
        ),
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the symlink + git-config actions without touching anything.",
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        help="Accept all confirmation prompts (no prompts today; audit-cli §2).",
    )
    def hooks_enable_pre_commit(target, force, dry_run, yes):
        del yes  # reserved for audit-cli §2 conformance; no prompts today.
        project = Path(target)
        source, deploy_rel = KNOWN_HOOKS["pre_commit"]

        if dry_run:
            click.echo(f"would install   pre_commit  →  {project / deploy_rel}")
            current = read_hookspath(project)
            planned = plan_hookspath(current, force=force)
            if planned == WIRED:
                click.echo(
                    f"would no-op     core.hooksPath = {HOOKS_DIR} (already wired)"
                )
            elif planned in (CONFIGURED, NO_GIT):
                click.echo(
                    f"would configure core.hooksPath = {HOOKS_DIR} "
                    f"(currently unset; in {project})"
                )
            elif planned == FORCED:
                click.echo(
                    f"would force     core.hooksPath = {HOOKS_DIR} "
                    f"(was {current!r}; --force given)"
                )
            else:
                click.echo(
                    f"would refuse    core.hooksPath = {current!r} already set "
                    f"(re-run with --force to overwrite)"
                )
            return

        status = _install_one("pre_commit", source, deploy_rel, project, force)
        click.echo(f"{install_symbol(status)}  pre_commit  →  {project / deploy_rel}")
        if status == "refused":
            click.echo(
                click.style(
                    "  (a non-symlink file exists at .githooks/pre-commit; "
                    "pass --force to overwrite, or remove it manually.)",
                    fg="red",
                ),
                err=True,
            )
            raise SystemExit(1)

        _report_wiring(project, *wire_hookspath(project, force=force))


__all__ = ["register_pre_commit"]

# EOF
