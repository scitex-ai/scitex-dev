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
                "from `--repo`, else the registry's `local_path`. "
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
            "Repo root to audit (defaults to the registry's local_path or "
            "the installed package's location). Use `--path` when running "
            "from a git worktree so the audit sees the worktree's source "
            "instead of the editable install — lets worktree agents "
            "self-verify before pushing. `--repo` is a legacy alias."
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
        from pathlib import Path

        from ....._ecosystem import ECOSYSTEM
        from ....audit import _api as _cli_audit_api

        repo = Path(repo_path).expanduser() if repo_path else None
        if repo is None:
            local = ECOSYSTEM.get(distribution, {}).get("local_path")
            if local:
                cand = Path(local).expanduser()
                if cand.is_dir():
                    repo = cand

        raise SystemExit(
            _cli_audit_api.audit_api(
                distribution,
                json_out=json_out,
                rules=set(rules) if rules else None,
                repo_root=repo,
            )
        )


__all__ = ["register"]
