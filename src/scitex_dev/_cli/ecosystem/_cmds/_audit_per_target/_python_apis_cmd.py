#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `audit-python-apis` — Python API surface auditor."""

import click

from ....._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(ecosystem):
    @ecosystem.command(
        "audit-python-apis",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Check a package's Python API against the §1-§5 audit checklist.",
            description=(
                "Honours per-project rule scoping the same way "
                "`audit-project` does: `.scitex/dev/config.yaml` "
                "`audit.skip` defers specific PA rules (e.g. "
                "PA-306/PA-307) and a `django` project-type relaxes "
                "PA-306 (no-mocks) to a warning. The repo root is taken "
                "from `--path`/`--repo`, else the CURRENT checkout when "
                "the cwd is inside a checkout of DISTRIBUTION, else the "
                "registry's `local_path`. "
                "Foundation rules (PA<§><idx>): PA-101-104 (§1 "
                "naming/visibility), PA-201-203 (§2 version), PA-301 "
                "(§3 lazy imports), PA-501 (§5 future annotations). See "
                "general/03_interface/01_python-api/12_audit-checklist.md.",
            ),
            examples=(
                Example("{prog} ecosystem audit-python-apis scitex-io", "One package."),
                Example(
                    "{prog} ecosystem audit-python-apis scitex-io --json",
                    "Structured JSON output.",
                ),
                Example(
                    "{prog} ecosystem audit-python-apis scitex-io --rule PA-101 --rule PA-202",
                    "Restrict to specific rules.",
                ),
            ),
        ),
    )
    @click.argument("distribution")
    @click.option(
        "--path",
        "--repo",
        "repo_path",
        type=click.Path(exists=True, file_okay=False, dir_okay=True),
        default=None,
        help=(
            "Repo root to audit — always wins when given. Without it, "
            "resolution is deterministic: the CURRENT checkout (git "
            "toplevel of the cwd, when its pyproject [project].name "
            "matches DISTRIBUTION — covers worktrees and CI checkouts), "
            "else the registry's local_path, else the installed "
            "package's location. `--repo` is a legacy alias."
        ),
    )
    @click.option("--json", "json_out", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Restrict to specific rule codes (e.g. --rule PA-101). Repeatable.",
    )
    def ecosystem_audit_python_apis(distribution, repo_path, json_out, rules):
        from ....audit import _api as _cli_audit_api
        from ....audit._target_tree import resolve_target_tree

        # Deterministic target-tree resolution (operator directive
        # 2026-07-21): explicit --path > current checkout (cwd git
        # toplevel, incl. linked worktrees) > registry local_path.
        repo, _resolved_via = resolve_target_tree(distribution, repo_path)

        raise SystemExit(
            _cli_audit_api.audit_api(
                distribution,
                json_out=json_out,
                rules=set(rules) if rules else None,
                repo_root=repo,
            )
        )


__all__ = ["register"]
