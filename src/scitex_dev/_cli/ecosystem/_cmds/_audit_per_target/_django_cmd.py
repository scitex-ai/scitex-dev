#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `audit-django` — companion to `audit-project` for Django apps.

Checks the repo against ADR 0002 (scitex-django-app-standard);
scitex-hub is the green reference. Non-Django packages are skipped
cleanly.
"""

import click

from ....._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(ecosystem):
    @ecosystem.command(
        "audit-django",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary='Check a Django app against the canonical "apps and config" layout.',
            description=(
                "Django project auditor (ADR 0002). Foundation rules "
                "(DJ<§><idx>): DJ-101-110 (§1 Django project in "
                "`config/`: settings package + env-loader, urls, "
                "asgi/wsgi, manage.py default), DJ-201-204 (§2 apps "
                "under `apps/`: infra/workspace, AppConfig), DJ-301-302 "
                "(§3 project `templates/` + `static/`), DJ-401-402 (§4 "
                "`src/scitex_<name>/` pip package sibling, not "
                "nested), DJ-501-502 (§5 web stack in the `[all]` "
                "extra, no `[django]` sub-extra). scitex-hub is the "
                "reference implementation and passes by definition; "
                "non-Django packages (no `manage.py`) are skipped. See "
                "docs/adr/0002-scitex-django-app-standard.md in "
                "scitex-hub.",
            ),
            examples=(
                Example("{prog} ecosystem audit-django scitex-hub", "One package."),
                Example(
                    "{prog} ecosystem audit-django scitex-hub --json",
                    "Structured JSON output.",
                ),
                Example(
                    "{prog} ecosystem audit-django scitex-orochi --severity warning",
                    "Include warning-level findings.",
                ),
                Example(
                    "{prog} ecosystem audit-django scitex-hub --rule DJ-101",
                    "Restrict to a specific rule.",
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
        help="Restrict to specific rule codes (e.g. --rule DJ-101). Repeatable.",
    )
    @click.option(
        "--severity",
        type=click.Choice(["error", "warning", "info"]),
        default="error",
        show_default=True,
        help=(
            "Minimum severity floor. 'error' prints E findings only and exits 1 "
            "iff >=1 E. 'warning' prints E+W. 'info' prints everything. "
            "W/I findings never fail CI on their own."
        ),
    )
    def ecosystem_audit_django(distribution, repo_path, json_out, rules, severity):
        from pathlib import Path

        from ....._ecosystem import ECOSYSTEM
        from ....audit import _django as _cli_audit_django

        repo = Path(repo_path).expanduser() if repo_path else None
        if repo is None:
            local = ECOSYSTEM.get(distribution, {}).get("local_path")
            if local:
                cand = Path(local).expanduser()
                if cand.is_dir():
                    repo = cand

        raise SystemExit(
            _cli_audit_django.audit_django(
                distribution,
                repo=repo,
                json_out=json_out,
                rules=set(rules) if rules else None,
                severity=severity,
            )
        )


__all__ = ["register"]
