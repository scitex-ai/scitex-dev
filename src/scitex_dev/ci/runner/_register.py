"""``scitex-dev ci runner register <repo>`` — thin alias of the canonical
CI mechanism (``scitex-dev ecosystem ci-template apply``) + CI_RUNS_ON var.

This command used to copy its OWN ``ci.yml.template`` (the in-SIF
single-CI body) — a second canonical template body that drifted against
``scitex_dev._ecosystem.ci_template``. That body is DELETED (operator
decision, 2026-07-21: one canonical shape = the thin org-reusable
caller); the workflow file is now rendered/deployed exclusively by
``ci_template.apply``, and this verb only adds the runner-selection
Actions Variable on top.
"""

from __future__ import annotations

import subprocess

import click

from ..._ecosystem.ci_template import (
    ApplyError,
    BranchProtectionGateError,
    apply as _ci_template_apply,
)
from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from . import config

#: The one sanctioned CI_RUNS_ON default — self-hosted only, NEVER
#: ubuntu-latest (PS-169). Must match the default documented in
#: ``ci_template/templates/ci.yml.tmpl``.
CI_RUNS_ON_DEFAULT = '["self-hosted","Linux","X64","scitex-ci"]'


def register(group: click.Group) -> None:
    @group.command(
        "register",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Register a repo with the canonical scitex CI caller.",
            description=(
                "Thin alias of `ecosystem ci-template apply` + the "
                "CI_RUNS_ON Actions Variable.\n"
                "\n"
                "Steps:\n"
                "  1. Deploy .github/workflows/ci.yml via the canonical "
                "ci-template mechanism (thin caller delegating to "
                "scitex-ai/.github@main; deletes superseded workflows).\n"
                f"  2. Set Actions Variable CI_RUNS_ON to '{CI_RUNS_ON_DEFAULT}'.\n"
                "  3. Print the fork-PR approval reminder (no repo settings "
                "are mutated)."
            ),
            examples=(
                Example(
                    "{prog} ci runner register ../scitex-stats --yes",
                    "Register a repo non-interactively.",
                ),
                Example(
                    "{prog} ci runner register ../figrecipe --dry-run",
                    "Preview without changing anything.",
                ),
            ),
        ),
    )
    @click.argument(
        "repo_path",
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print what would be done without making changes.",
    )
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help="Skip the confirmation prompt (required for non-interactive use).",
    )
    @click.option(
        "--skip-required-check-gate",
        is_flag=True,
        default=False,
        help="DANGEROUS — bypass the branch-protection compatibility gate "
        "(passed through to ci-template apply). Debugging only.",
    )
    def register_cmd(
        repo_path: str, dry_run: bool, yes: bool, skip_required_check_gate: bool
    ) -> None:
        cfg = config.load_runner_config()
        config.get_gh_token(cfg)

        # Determine the repo owner/name from the local git remote
        repo_result = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if repo_result.returncode != 0:
            raise click.ClickException(
                f"Not a git repo (or no 'origin' remote): {repo_path}"
            )

        remote_url = repo_result.stdout.strip()
        # Parse owner/repo from git URL
        # (SSH: git@github.com:owner/repo.git, HTTPS: https://github.com/owner/repo.git)
        import re as _re

        m = _re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote_url)
        if not m:
            raise click.ClickException(
                f"Could not parse owner/repo from remote: {remote_url}"
            )
        owner, repo = m.group(1), m.group(2)

        # Mutating from here on — refuse without --yes (no interactive prompt).
        if not dry_run and not yes:
            raise click.ClickException(
                f"Refusing to register {owner}/{repo} without --yes/-y "
                "(writes ci.yml, deletes superseded workflows, sets the "
                "CI_RUNS_ON Actions Variable). Re-run with --yes to "
                "confirm, or --dry-run to preview."
            )

        # Step 1: Deploy the canonical thin caller via the ONE mechanism.
        try:
            result = _ci_template_apply(
                repo_path,
                dry_run=dry_run,
                skip_required_check_gate=skip_required_check_gate,
            )
        except BranchProtectionGateError as exc:
            raise click.ClickException(str(exc))
        except ApplyError as exc:
            raise click.ClickException(str(exc))

        prefix = "[dry-run] Would write" if dry_run else "Wrote"
        for p in result.written_paths:
            click.echo(f"{prefix}: {p}")
        prefix = "[dry-run] Would delete" if dry_run else "Deleted"
        for p in result.deleted_paths:
            click.echo(f"{prefix}: {p}")

        if dry_run:
            click.echo(f"[dry-run] Would set Actions Variable on {owner}/{repo}:")
            click.echo(f"  CI_RUNS_ON = '{CI_RUNS_ON_DEFAULT}'")
            return

        # Step 2: Set the runner-selection Actions Variable via gh api.
        click.echo(f"Setting Actions Variable CI_RUNS_ON on {owner}/{repo}...")
        var_result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{owner}/{repo}/actions/variables/CI_RUNS_ON",
                "-X",
                "POST",
                "-f",
                f"value={CI_RUNS_ON_DEFAULT}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if var_result.returncode != 0:
            click.echo(f"  Warning: {var_result.stderr.strip()[:100]}")

        # Step 3: Fork-PR approval is a manual repo setting — do NOT mutate
        # the repo's settings here.
        click.echo(
            "  (Set fork-PR approval manually: repo Settings → Actions → "
            "Require approval for all outside collaborators)"
        )

        click.echo(f"\n✓ {owner}/{repo} registered with the canonical scitex CI.")
        click.echo("  Workflow: .github/workflows/ci.yml (org-reusable caller)")
        click.echo(f"  Variable: CI_RUNS_ON = '{CI_RUNS_ON_DEFAULT}'")


# EOF
