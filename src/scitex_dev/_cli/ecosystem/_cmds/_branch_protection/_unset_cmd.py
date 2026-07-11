#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `unset-branch-protection` — rollback for `update-branch-protection`.

`unset` is already declared a sanctioned `transitive_verbs` entry in
`.scitex/dev/cli-audit-dict.yaml` (the set/unset pair reads naturally as
opposites; Moby's POS catalog just doesn't carry `unset` at all), so
this command needs no rename — only the CliHelp conversion.
"""

from __future__ import annotations

import json

import click

from ....._ecosystem.help_spec import CliHelp, Example, SpecCommand
from . import _helpers


def register(ecosystem):
    @ecosystem.command(
        "unset-branch-protection",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Remove branch protection on DISTRIBUTION (rollback for update-).",
            description=(
                "Deletes the protection rule on DISTRIBUTION's `develop` "
                "and/or `main` branch. --dry-run is the default; pass "
                "--execute to actually DELETE.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem unset-branch-protection scitex-dev",
                    "Preview (dry-run).",
                ),
                Example(
                    "{prog} ecosystem unset-branch-protection scitex-dev --execute",
                    "Actually remove protection.",
                ),
            ),
        ),
    )
    @click.argument("distribution")
    @click.option(
        "--branch",
        type=click.Choice(["develop", "main", "both"]),
        default="both",
        help="Which branch to unprotect. Default: both.",
    )
    @click.option(
        "--execute",
        "-y",
        "--yes",
        "execute",
        is_flag=True,
        help="Actually DELETE the protection rule.",
    )
    @click.option("--json", "json_out", is_flag=True)
    def ecosystem_unset_branch_protection(distribution, branch, execute, json_out):
        owner_repo = _helpers._resolve_owner_repo(distribution)
        if owner_repo is None:
            click.echo(f"error: '{distribution}' not in ECOSYSTEM", err=True)
            raise SystemExit(2)

        targets = ["develop", "main"] if branch == "both" else [branch]
        exit_code = 0
        for tgt in targets:
            if not _helpers._branch_exists(owner_repo, tgt):
                if json_out:
                    click.echo(
                        json.dumps(
                            {"branch": tgt, "action": "skip", "reason": "no-branch"}
                        )
                    )
                else:
                    click.echo(
                        f"skip  {distribution}: branch '{tgt}' does not exist on origin",
                        err=True,
                    )
                continue
            if not execute:
                if json_out:
                    click.echo(json.dumps({"branch": tgt, "action": "dry-run"}))
                else:
                    click.echo(
                        f"DRY-RUN {distribution}@{tgt}: "
                        f"DELETE repos/{owner_repo}/branches/{tgt}/protection"
                    )
                continue
            rc, out = _helpers._gh_api(
                "DELETE", f"repos/{owner_repo}/branches/{tgt}/protection"
            )
            if rc != 0:
                if json_out:
                    click.echo(
                        json.dumps(
                            {
                                "branch": tgt,
                                "action": "error",
                                "rc": rc,
                                "stderr": out,
                            }
                        )
                    )
                else:
                    click.echo(
                        f"error  {distribution}@{tgt}: DELETE failed (rc={rc}): {out}",
                        err=True,
                    )
                exit_code = 1
                continue
            if json_out:
                click.echo(json.dumps({"branch": tgt, "action": "unset", "ok": True}))
            else:
                click.echo(f"ok    {distribution}@{tgt}: protection removed")
        raise SystemExit(exit_code)


__all__ = ["register"]
