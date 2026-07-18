#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `audit-project` — project-structure auditor."""

import click

from ....._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(ecosystem):
    @ecosystem.command(
        "audit-project",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Check a package's project-structure against the canonical layout.",
            description=(
                "Foundation rules (PS<§><idx>): PS-101-104 (§1 "
                "top-level layout: pyproject, forbidden dirs, junk), "
                "PS-201-206 (§2 src <-> tests mirror: parent, mirror, "
                "prefix, orphan, placeholder), PS-301-303 (§3 tests/ "
                "subdir convention: htmlcov, unknown subdirs, "
                "examples), PS-401-402 (§4 docs/ structure: to_claude "
                "gitignored, assets location). See "
                "_skills/general/02_package/01_project-structure-root.md "
                "for the full convention (ditto "
                "_skills/scientific/02_research-project_01_project-structure-root.md "
                "for research-project layout). Templates and datasets "
                "are exempt from §2.",
            ),
            examples=(
                Example("{prog} ecosystem audit-project scitex-io", "One package."),
                Example(
                    "{prog} ecosystem audit-project scitex-dev --json",
                    "Structured JSON output.",
                ),
                Example(
                    "{prog} ecosystem audit-project scitex-stats --rule PS-108",
                    "Restrict to a specific rule.",
                ),
                Example(
                    "{prog} ecosystem audit-project scitex-io --severity warning",
                    "Include warning-level findings.",
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
        help="Restrict to specific rule codes (e.g. --rule PS-201). Repeatable.",
    )
    @click.option(
        "--severity",
        type=click.Choice(["error", "warning", "info"]),
        default="error",
        show_default=True,
        help=(
            "Minimum severity floor. 'error' prints E findings only and exits 1 "
            "iff ≥1 E. 'warning' prints E+W. 'info' prints everything. "
            "W/I findings never fail CI on their own."
        ),
    )
    def ecosystem_audit_project(distribution, repo_path, json_out, rules, severity):
        from pathlib import Path

        from ....._ecosystem import ECOSYSTEM
        from ....audit import _project as _cli_audit_project

        repo = Path(repo_path).expanduser() if repo_path else None
        if repo is None:
            local = ECOSYSTEM.get(distribution, {}).get("local_path")
            if local:
                cand = Path(local).expanduser()
                if cand.is_dir():
                    repo = cand

        raise SystemExit(
            _cli_audit_project.audit_project(
                distribution,
                repo=repo,
                json_out=json_out,
                rules=set(rules) if rules else None,
                severity=severity,
            )
        )


__all__ = ["register"]
