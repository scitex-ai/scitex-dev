#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `update-branch-protection` (+ deprecated `set-branch-protection` alias).

Brand-wide GitHub branch-protection management. PR #117 raced past CI by
auto-merging before required checks completed; an ecosystem survey then
showed 8 of 10 sampled repos have NO required_status_checks on `develop`.
This module makes "CI-green is the only gate" actually enforced by
configuring branch protection consistently across the fleet.

Policy (from lead msg a3c59d1a):

  required_status_checks       = 6 CI contexts, intersected with what the
                                  repo's workflows actually publish:
                                    pytest-matrix-on-ubuntu-py3.11
                                    pytest-matrix-on-ubuntu-py3.12
                                    pytest-matrix-on-ubuntu-py3.13
                                    sphinx
                                    import-smoke-on-ubuntu-py3-12
                                    audit
  strict                       = False  (don't serialise the parallel fleet
                                          on rebase-before-merge churn)
  enforce_admins (develop)     = True   (the #117 race fix; nobody bypasses
                                          CI on the integration branch)
  enforce_admins (main)        = False  (release flow needs the admin merge
                                          + tag-push to fire PyPI; locking
                                          admin out would wedge releases)
  required_pull_request_reviews = OMIT  (CI-green is the only gate)
  required_linear_history      = True   (matches the squash-merge convention)
  allow_force_pushes           = False
  allow_deletions               = False

CLAssistant is deliberately HELD OUT of the required set today — the bot
has a documented transient timing failure mode; making it blocking would
let a bot hiccup wedge the fleet's auto-merge. Keep it as a non-blocking
check; revisit when stable.

Operations
----------
Defaults to --dry-run. Pass --execute (or -y / --yes) to actually PUT.
The PUT body is computed live from the repo's current workflows so
additions land automatically; the required-set contexts that the repo
doesn't publish are silently dropped (e.g. scitex-orochi has no develop
branch — main-only operation), preventing "required check that never
runs" deadlocks.

The first execution lands on scitex-dev ITSELF; fleet-wide rollout waits
on operator confirm via lead. Sibling `unset-branch-protection` (in
`_unset_cmd.py`) is the rollback path.

Rename note (§1f, 2026-07-11): the command was `set-branch-protection`;
`set` is reserved (doctrine 06_noun-verb-catalog) for single-key config
writes, and this command writes a whole multi-key protection policy, so
the canonical verb is `update`. `set-branch-protection` stays registered
as a warn-phase deprecated alias (see the bottom of this file).
"""

from __future__ import annotations

import click

from ....._ecosystem.click_compat import deprecated_alias
from ....._ecosystem.help_spec import CliHelp, Example, SpecCommand
from . import _helpers


def register(ecosystem):
    @ecosystem.command(
        "update-branch-protection",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Apply the brand-wide branch-protection policy to DISTRIBUTION.",
            description=(
                "Applies the policy (lead msg a3c59d1a) to DISTRIBUTION's "
                "`develop` and/or `main` branch. Required contexts are "
                "computed live from the repo's published workflows so we "
                "never demand a check the repo cannot publish. --dry-run "
                "is the default; pass --execute to actually PUT. Pass "
                "`all` as DISTRIBUTION to roll out across every "
                "ECOSYSTEM repo. With --deletion-only this is the "
                "fleet-wide standard baseline that keeps every `develop` "
                "un-deletable without blocking CI's commit-back push.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem update-branch-protection scitex-dev",
                    "Preview (dry-run).",
                ),
                Example(
                    "{prog} ecosystem update-branch-protection scitex-dev "
                    "--branch develop --execute",
                    "Apply to develop only.",
                ),
                Example(
                    "{prog} ecosystem update-branch-protection scitex-io --dry-run",
                    "Explicit dry-run.",
                ),
            ),
        ),
    )
    @click.argument("distribution")
    @click.option(
        "--branch",
        type=click.Choice(["develop", "main", "both"]),
        default="both",
        help="Which branch to protect. Default: both.",
    )
    @click.option(
        "--deletion-only",
        is_flag=True,
        help="Apply only the minimal un-deletable baseline (no required checks / "
        "enforce-admins) so CI's own pushes to develop are not blocked. This is "
        "the fleet-wide standard; omit for the full brand-wide policy.",
    )
    @click.option(
        "--execute",
        "-y",
        "--yes",
        "execute",
        is_flag=True,
        help="Actually PUT the protection rule. Without this, prints the "
        "planned PUT body and exits.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help=(
            "Explicitly request the preview-only behavior that is ALREADY "
            "the default when --execute is omitted. Provided for "
            "audit-cli §2 / script self-documentation, and as a safety "
            "override: if both --dry-run and --execute are passed, "
            "--dry-run wins (no PUT is issued)."
        ),
    )
    @click.option(
        "--json",
        "json_out",
        is_flag=True,
        help="Emit one JSON object per branch instead of human-readable text.",
    )
    def ecosystem_update_branch_protection(
        distribution, branch, deletion_only, execute, dry_run, json_out
    ):
        targets = ["develop", "main"] if branch == "both" else [branch]
        dists = (
            _helpers._all_distributions() if distribution == "all" else [distribution]
        )

        exit_code = 0
        for dist in dists:
            rc = _helpers._apply_one(
                dist,
                targets,
                deletion_only=deletion_only,
                execute=execute and not dry_run,
                json_out=json_out,
            )
            exit_code = max(exit_code, rc)
        raise SystemExit(exit_code)

    # `set-branch-protection` → `update-branch-protection` rename (§1f:
    # `set` is reserved for single-key config writes; this command
    # writes a whole multi-key policy, so `update` is canonical).
    deprecated_alias(
        ecosystem,
        "set-branch-protection",
        target="update-branch-protection",
        remove_in="0.32",
        phase="warn",
    )


__all__ = ["register"]
