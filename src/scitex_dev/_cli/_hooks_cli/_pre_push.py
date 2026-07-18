"""``hooks enable-pre-push`` — install the gate AND wire ``core.hooksPath``.

The 2026-06-15 red-green-doctrine push pinned the "push → CI red → push
fix → CI red again" merry-go-round. The pre-push gate runs the SAME
audit-conformance check CI runs (``scitex-dev ecosystem audit-all``, the
one ``scitex-dev ecosystem install-audit-gate`` wires into
``tests/develop/test_audit.py`` so local + CI agree byte-for-byte) PLUS a
diff-scoped ruff F401/F811 + import-smoke + testmon-scoped pytest subset
that excludes heavy markers. The local gate is the fast ~60s check, not a
CI replacement — heavy tests keep going through CI.

The gate ships as ``scitex_dev/_hooks/pre-push.sh`` (alongside
``run_lint.sh``). ``enable-pre-push`` installs it as a SYMLINK at
``<target>/.githooks/pre-push`` AND runs ``git -C <target> config
core.hooksPath .githooks``. Without the second step, a script at
``.githooks/pre-push`` is a no-op — git only looks under ``.git/hooks/``
by default. Doing both halves in one command means operators never ship a
half-installed gate that silently no-ops.

Bypass is intentionally NOT disabled:
- ``SCITEX_DEV_SKIP_PREPUSH=1 git push`` — one-shot env var
- ``git push --no-verify`` — git's native escape hatch
Both print a notice so the choice is visible in transcripts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ._registry import KNOWN_HOOKS, _install_one, install_symbol


def register_pre_push(hooks_group) -> None:
    """Attach the ``enable-pre-push`` leaf to ``hooks_group``."""

    @hooks_group.command(
        "enable-pre-push",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Install the pre-push gate AND wire core.hooksPath.",
            description=(
                "Does two things in one step so operators never ship a "
                "half-installed gate that silently no-ops: (1) symlinks the "
                "bundled `pre-push.sh` into `<target>/.githooks/pre-push`, "
                "and (2) runs `git -C <target> config core.hooksPath "
                ".githooks`. Without step 2 a script at `.githooks/pre-push` "
                "does nothing — git only looks under `.git/hooks/` by "
                "default. The gate then runs locally before every `git "
                "push`: `scitex-dev ecosystem audit-all <pkg> --path "
                "<target>` plus a diff-scoped ruff F401/F811 + import-smoke "
                "+ testmon subset. Heavy tests (slow / integration / "
                "network) stay in CI per the red-green doctrine — the local "
                "gate is the FAST ~60s check, not a CI replacement. "
                "core.hooksPath is ADDITIVE-then-refuse: unset -> set to "
                ".githooks; already .githooks -> no-op; anything else -> "
                "REFUSE unless --force (never silently clobber an operator's "
                "chosen hooks dir). Bypass is intentionally NOT disabled: "
                "`SCITEX_DEV_SKIP_PREPUSH=1 git push` or `git push "
                "--no-verify` — both print a notice so the choice is visible "
                "in transcripts.",
            ),
            examples=(
                Example(
                    "{prog} hooks enable-pre-push --target ~/proj/figrecipe",
                    "installed pre_push -> .githooks/pre-push; configured core.hooksPath.",
                ),
                Example(
                    "{prog} hooks enable-pre-push --target . --dry-run",
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
        help="Repo root to install the pre-push gate into.",
    )
    @click.option(
        "--force",
        is_flag=True,
        help=(
            "Overwrite (a) an existing non-symlink `.githooks/pre-push` "
            "file OR (b) an operator-chosen `core.hooksPath` pointing "
            "anywhere other than `.githooks`. By default we refuse both so "
            "an operator-edited hook / hooks dir is never silently "
            "clobbered. The prior values are printed when --force takes "
            "effect."
        ),
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help=(
            "Print the symlink + git-config actions without touching the "
            "filesystem or running `git config`. audit-cli §2 — every "
            "mutating verb must expose --dry-run."
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
        del yes  # reserved for audit-cli §2 conformance; no prompts today.
        project = Path(target)
        source, deploy_rel = KNOWN_HOOKS["pre_push"]

        def _current_hookspath() -> str | None:
            """Read core.hooksPath; None if git is unavailable."""
            try:
                return subprocess.run(
                    ["git", "-C", str(project), "config", "--get", "core.hooksPath"],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip()
            except FileNotFoundError:
                return None

        if dry_run:
            click.echo(f"would install   pre_push  →  {project / deploy_rel}")
            current = _current_hookspath()
            if current == ".githooks":
                click.echo(
                    "would no-op     core.hooksPath = .githooks (already wired)"
                )
            elif not current:
                click.echo(
                    f"would configure core.hooksPath = .githooks "
                    f"(currently unset; in {project})"
                )
            elif force:
                click.echo(
                    f"would force     core.hooksPath = .githooks "
                    f"(was {current!r}; --force given)"
                )
            else:
                click.echo(
                    f"would refuse    core.hooksPath = {current!r} already set "
                    f"(re-run with --force to overwrite)"
                )
            return

        # Step 1: install the symlink (reuse the shared helper so status
        # words stay consistent with `hooks install`).
        status = _install_one("pre_push", source, deploy_rel, project, force)
        click.echo(f"{install_symbol(status)}  pre_push  →  {project / deploy_rel}")
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

        # Step 2: wire core.hooksPath — ADDITIVE-then-refuse.
        current = _current_hookspath()
        if current is None:
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

        if current and current != ".githooks" and not force:
            click.echo(
                click.style(
                    f"refused    core.hooksPath already set to "
                    f"{current!r}; refusing to overwrite without --force",
                    fg="red",
                ),
                err=True,
            )
            click.echo(
                click.style(
                    "  Re-run with --force to overwrite, or unset first:",
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

        if current and current != ".githooks":
            prev_note = f" (forced; was: {current!r})"
            verb = click.style("forced    ", fg="yellow")
        else:
            prev_note = " (was: unset — git default)"
            verb = click.style("configured", fg="green")
        click.echo(f"{verb}  core.hooksPath = .githooks{prev_note}")


__all__ = ["register_pre_push"]
