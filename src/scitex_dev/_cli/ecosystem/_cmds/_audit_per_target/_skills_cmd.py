#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `audit-skills` — `_skills/<pip-name>/` tree auditor."""

import click

from ....._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(ecosystem):
    @ecosystem.command(
        "audit-skills",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Check a package's _skills/<pip-name>/ against the §1-§FM checklist.",
            description=(
                "Foundation rules (SK<§><idx>): SK-101-104 (§1 layout), "
                "SK-201-203 (§2 naming), SK-210-211 (§2a no "
                "header/footer above frontmatter), SK-301-302 (§3 "
                "SKILL.md as index), SK-401 (§4 leaf size), SK-601 (§6 "
                "no `import scitex as stx`), SK-701-704 (frontmatter "
                "required fields). See "
                "general/03_interface/04_skills/12_quality-checklist.md.",
            ),
            examples=(
                Example("{prog} ecosystem audit-skills scitex-io", "One package."),
                Example(
                    "{prog} ecosystem audit-skills scitex-io --json",
                    "Structured JSON output.",
                ),
                Example(
                    "{prog} ecosystem audit-skills scitex-io --rule SK-210 --rule SK-211",
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
            "package's location. `--repo` is a legacy alias. The skills "
            "tree is read from `<root>/src/<import_name>/_skills/`."
        ),
    )
    @click.option("--json", "json_out", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Restrict to specific rule codes (e.g. --rule SK-210). Repeatable.",
    )
    @click.option(
        "--fix",
        is_flag=True,
        help=(
            "Auto-fix mechanically resolvable rules (SK-705/SK-709/SK-710). "
            "Rewrites only frontmatter; idempotent."
        ),
    )
    def ecosystem_audit_skills(distribution, repo_path, json_out, rules, fix):
        from ....audit import _skills as _cli_audit_skills
        from ....audit._target_tree import resolve_target_tree

        # Deterministic target-tree resolution (operator directive
        # 2026-07-21): explicit --path > current checkout (cwd git
        # toplevel, incl. linked worktrees) > registry local_path. Shared
        # with audit-project/django/python-apis so --path wins uniformly.
        repo, resolved_via = resolve_target_tree(distribution, repo_path)

        raise SystemExit(
            _cli_audit_skills.audit_skills(
                distribution,
                json_out=json_out,
                rules=set(rules) if rules else None,
                fix=fix,
                repo_root=repo,
                resolved_via=resolved_via,
            )
        )


__all__ = ["register"]
