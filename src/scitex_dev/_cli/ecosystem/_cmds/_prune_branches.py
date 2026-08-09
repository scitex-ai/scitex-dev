#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `prune-branches` — the config-gated branch GC's CLI surface.

Click only. Every decision lives in :mod:`scitex_dev.hygiene`, so this
verb, the ``branch-gc`` cron job and any future caller share ONE predicate
rather than three drifting copies.

Contrast with the older `prune-merged` in this same directory, which this
command is intended to supersede: that one has no age floor anywhere in
the file and finds landed branches with the ancestor check alone, so in a
squash-merging repo it reaches ~9% of branches. This one has a hard,
un-lowerable age floor, three landing sources, five safety legs, a
verified bundle before any delete, and is OFF unless two config files
independently say so.
"""

from __future__ import annotations

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ._sync_helpers import parse_package_filter, resolve_repo, selected_packages

_MARK = {"deleted": "x", "would-delete": ".", "kept": "-"}


def _repos_for(package, repo_paths) -> list[str]:
    """Explicit --repo paths win; otherwise the ECOSYSTEM selection."""
    if repo_paths:
        return [str(path) for path in repo_paths]
    pkg_filter = parse_package_filter(package)
    return [
        str(resolve_repo(pkg, info))
        for pkg, info in selected_packages(pkg_filter)
        if resolve_repo(pkg, info).is_dir()
    ]


def register(ecosystem):
    @ecosystem.command(
        "prune-branches",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Config-gated local-branch GC (DEFAULT OFF, dry-run default).",
            description=(
                "Deletes ONLY local refs/heads/* refs, and only when all "
                "five safety legs pass: LANDED (ancestor OR patch-"
                "equivalence OR merged PR — never `git branch --merged` "
                "alone, which is blind to squash-merges), OLD (a hard "
                "14-day floor no config can lower), UNCHECKED-OUT in any "
                "worktree, UNPROTECTED (main/master/develop/release/* and "
                "no open PR), and NOT the substrate of any in-flight card. "
                "Any leg that cannot be evaluated reads as KEEP, never as "
                "pass. OFF unless BOTH <repo>/.scitex/dev/config.yaml and "
                "~/.scitex/dev/config.yaml set cleanup.branches.enabled to "
                "literal true; even then --apply is required. Before any "
                "delete a self-contained git bundle is written under "
                "<repo>/.scitex/dev/runtime/branch-gc/<ts>/ and VERIFIED; "
                "if it cannot be verified, nothing is deleted. The restore "
                "command is printed. No remote branch, tag, stash, reflog "
                "or worktree is ever touched."
            ),
            examples=(
                Example(
                    "{prog} ecosystem prune-branches --repo .",
                    "Dry-run this repo: what it would delete and what it protected.",
                ),
                Example(
                    "{prog} ecosystem prune-branches -p scitex-dev --json",
                    "Dry-run one ecosystem package, structured output.",
                ),
                Example(
                    "{prog} ecosystem prune-branches --repo . --apply",
                    "Delete (requires cleanup.branches.enabled in BOTH configs).",
                ),
                Example(
                    "{prog} ecosystem prune-branches --repo . --max-delete 5",
                    "Bound the pass; deferred branches are listed, never hidden.",
                ),
            ),
        ),
    )
    @click.option(
        "--package",
        "-p",
        multiple=True,
        help="Limit to specific ecosystem packages (comma-separated or repeat).",
    )
    @click.option(
        "--repo",
        "repo_paths",
        multiple=True,
        type=click.Path(exists=True, file_okay=False),
        help="Operate on these repo paths instead of the ECOSYSTEM registry.",
    )
    @click.option(
        "--apply",
        "do_apply",
        is_flag=True,
        help="Actually delete (default is dry-run). Also requires the config gate.",
    )
    @click.option(
        "--max-delete",
        "max_delete",
        type=int,
        default=None,
        help="Bound deletions per repo. Deferred branches are REPORTED, not hidden.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
    def ecosystem_prune_branches(package, repo_paths, do_apply, max_delete, as_json):
        import json as _json
        import sys as _sys

        from ....hygiene import BranchGcOutcome, exit_code_for, gc_repo

        repos = _repos_for(package, repo_paths)
        outcome = BranchGcOutcome(
            results=tuple(
                gc_repo(repo, apply=do_apply, max_delete=max_delete) for repo in repos
            )
        )

        if as_json:
            click.echo(
                _json.dumps(
                    {
                        "apply": do_apply,
                        "summary": outcome.summary_line(),
                        "results": [r.to_dict() for r in outcome.results],
                    },
                    indent=2,
                    default=str,
                )
            )
            _sys.exit(exit_code_for(outcome))

        _render(outcome, do_apply)
        _sys.exit(exit_code_for(outcome))

    def _render(outcome, do_apply):
        for result in outcome.results:
            _render_one(result, do_apply)
        click.echo("")
        click.echo(outcome.summary_line(), err=True)
        if not do_apply:
            click.echo(
                "Dry run. --apply deletes, and ONLY if cleanup.branches.enabled "
                "is literally true in BOTH the repo and user config.",
                err=True,
            )

    def _render_one(result, do_apply):
        click.echo(f"{result.repo}:")
        if result.unreadable:
            click.echo(f"  UNKNOWN  could not read repo: {result.error}")
            return

        state = "ENABLED" if result.enabled else "DISABLED (default OFF)"
        click.echo(
            f"  config   {state}; age floor {result.min_age_days:g}d; "
            f"{result.count_before} local branch(es)"
        )
        if result.config_error:
            click.echo(f"  reason   {result.config_error}")
        if result.abort_reason:
            click.echo(f"  ABORTED  {result.abort_reason}")

        verb = "deleted" if do_apply and result.enabled else "would-delete"
        for verdict in result.candidates:
            mark = _MARK["deleted" if verdict.deleted else "would-delete"]
            via = (
                f"  (landed via {verdict.landed_source})"
                if verdict.landed_source
                else ""
            )
            click.echo(f"  {mark} {verb:12} {verdict.name}{via}")

        breakdown = result.keep_reason_breakdown
        if breakdown:
            detail = ", ".join(f"{k}={v}" for k, v in breakdown.items())
            click.echo(
                f"  {_MARK['kept']} protected   {len(result.kept)} kept: {detail}"
            )
        if result.exceeds_cap:
            click.echo(
                f"  DEGRADED {result.count_after} branches exceed the cap "
                f"of {result.cap} — the predicate is NOT relaxed to hit it."
            )
        if result.bundle_path:
            click.echo(f"  backup   {result.bundle_path}")
            click.echo(f"  restore  {result.restore_command}")


# EOF
