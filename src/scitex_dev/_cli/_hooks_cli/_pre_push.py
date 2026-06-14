"""``hooks enable-pre-push`` — install the gate AND wire ``core.hooksPath``.

The 2026-06-15 red-green-doctrine push pinned the "push → CI red →
push fix → CI red again" merry-go-round. The pre-push gate runs the
SAME audit-conformance check that
``scitex-dev ecosystem install-audit-gate`` wires into
``tests/develop/test_audit.py`` (so local + CI agree byte-for-byte)
PLUS a testmon-scoped pytest run that excludes heavy markers (the
local gate is the fast 60s check, not a CI replacement — heavy tests
keep going through CI).

The gate ships as ``scitex_dev/_hooks/pre-push.sh`` (alongside
``run_lint.sh``). ``enable-pre-push`` installs it as a SYMLINK at
``<target>/.githooks/pre-push`` AND runs
``git -C <target> config core.hooksPath .githooks``. Without the
second step, a script at ``.githooks/pre-push`` is a no-op — git only
looks under ``.git/hooks/`` by default. Doing both halves in one
command means operators never ship a half-installed gate that
silently no-ops.

Bypass is intentionally NOT disabled:
- ``SCITEX_DEV_SKIP_PREPUSH=1 git push`` — one-shot env var
- ``git push --no-verify`` — git's native escape hatch
Both print a notice so the choice is visible in transcripts.

Distributable: same symlink mechanism as ``run_lint``, so future
scitex-dev releases auto-propagate the gate to every project that
ran ``enable-pre-push`` once.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from ._registry import KNOWN_HOOKS, install_one


def register(hooks_group) -> None:
    """Attach the ``enable-pre-push`` leaf to ``hooks_group``."""

    @hooks_group.command(
        "enable-pre-push",
        short_help="Install the pre-push gate AND wire core.hooksPath.",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev hooks enable-pre-push --target ~/proj/figrecipe\n"
            "  $ scitex-dev hooks enable-pre-push --target . --dry-run\n"
            "\n"
            "Does two things in one step:\n"
            "  1. symlinks the bundled `pre-push.sh` into\n"
            "     `<target>/.githooks/pre-push`\n"
            "  2. runs `git -C <target> config core.hooksPath .githooks`\n"
            "\n"
            "The gate then runs locally before every `git push`:\n"
            "  - `scitex-dev ecosystem audit-all <pkg> --path <target>`\n"
            "  - `pytest --testmon -m 'not slow and not integration'`\n"
            "\n"
            "Heavy tests (slow / integration / network) stay in CI per\n"
            "the red-green doctrine — the local gate is the FAST 60s\n"
            "check that catches the obvious red, not a CI replacement.\n"
            "\n"
            "Bypass paths (intentionally NOT disabled — emergency hatch):\n"
            "  SCITEX_DEV_SKIP_PREPUSH=1 git push\n"
            "  git push --no-verify\n"
        ),
    )
    @click.option(
        "--target",
        "target",
        required=True,
        type=click.Path(file_okay=False, dir_okay=True, exists=True, resolve_path=True),
        help="Repo root to install the pre-push gate into.",
    )
    @click.option(
        "--force",
        is_flag=True,
        help=(
            "Overwrite an existing non-symlink `.githooks/pre-push` file. "
            "By default we refuse so an operator-edited hook is never "
            "silently clobbered."
        ),
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help=(
            "Print the symlink + git-config actions without touching "
            "the filesystem or running `git config`. audit-cli §2."
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
    def hooks_enable_pre_push(target, force, dry_run, yes):
        """Install the pre-push gate AND wire ``core.hooksPath`` so it fires.

        Without ``core.hooksPath`` pointing at ``.githooks``, dropping a
        script at ``.githooks/pre-push`` has no effect — git only looks
        in ``.git/hooks/`` by default. This command does both halves so
        operators don't ship a half-installed gate that silently no-ops.

        \b
        Example:
            $ scitex-dev hooks enable-pre-push --target ~/proj/figrecipe
            installed   pre_push  →  ~/proj/figrecipe/.githooks/pre-push
            configured  core.hooksPath = .githooks
        """
        del yes  # reserved for audit-cli §2 conformance
        project = Path(target)
        source, deploy_rel = KNOWN_HOOKS["pre_push"]

        if dry_run:
            click.echo(f"would install   pre_push  →  {project / deploy_rel}")
            click.echo(f"would configure core.hooksPath = .githooks (in {project})")
            return

        # Step 1: install the symlink. Reuse the same helper the
        # generic `hooks install` uses, so the up-to-date / refused /
        # forced status words stay consistent across surfaces.
        status = install_one("pre_push", source, deploy_rel, project, force)
        symbol = {
            "installed": click.style("installed ", fg="green"),
            "updated": click.style("updated   ", fg="green"),
            "up-to-date": click.style("up-to-date", fg="cyan"),
            "refused": click.style("refused   ", fg="red"),
            "forced": click.style("forced    ", fg="yellow"),
        }[status]
        click.echo(f"{symbol}  pre_push  →  {project / deploy_rel}")
        if status == "refused":
            click.echo(
                click.style(
                    "  (a non-symlink file exists at .githooks/pre-push; "
                    "pass --force to overwrite, or remove it manually.)",
                    fg="red",
                ),
                err=True,
            )
            raise SystemExit(1)

        # Step 2: wire core.hooksPath. We use `git -C <project>` so the
        # command works regardless of the CWD. If the project isn't a
        # git repo (or git is missing) we surface the failure clearly.
        try:
            current = subprocess.run(
                ["git", "-C", str(project), "config", "--get", "core.hooksPath"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
        except FileNotFoundError:
            click.echo(
                click.style(
                    "error: `git` binary not found on PATH; cannot wire "
                    "core.hooksPath. Install git and re-run.",
                    fg="red",
                ),
                err=True,
            )
            raise SystemExit(1)

        if current == ".githooks":
            click.echo(
                click.style(
                    "up-to-date  core.hooksPath = .githooks (already wired)",
                    fg="cyan",
                )
            )
            return

        rc = subprocess.run(
            ["git", "-C", str(project), "config", "core.hooksPath", ".githooks"],
            capture_output=True,
            text=True,
            check=False,
        )
        if rc.returncode != 0:
            click.echo(
                click.style(
                    f"error: `git config core.hooksPath` failed: "
                    f"{rc.stderr.strip() or rc.stdout.strip()}",
                    fg="red",
                ),
                err=True,
            )
            raise SystemExit(rc.returncode)

        prev_note = f" (was: {current})" if current else " (was: unset — git default)"
        click.echo(
            f"{click.style('configured', fg='green')}  "
            f"core.hooksPath = .githooks{prev_note}"
        )


__all__ = ["register"]
