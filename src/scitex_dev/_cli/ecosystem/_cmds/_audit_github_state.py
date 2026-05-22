#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `audit-github-state` — live GitHub-state audits.

Currently checks PS-172 (default-branch convention). Unlike
``audit-project`` (per-file working-tree rules), this command queries
GitHub state via ``gh api`` and so lives on the ecosystem audit path.
"""

import json

import click


def register(ecosystem):
    @ecosystem.command(
        "audit-github-state",
        epilog=(
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-github-state\n"
            "  $ scitex-dev ecosystem audit-github-state --json\n"
            "  $ scitex-dev ecosystem audit-github-state -p newb\n"
            "\n"
            "Live GitHub-state audit (uses `gh api`). PS-172 checks each\n"
            "repo's default branch == the convention (main). Honours\n"
            "GH_TOKEN from the environment. Exits 1 if any repo deviates\n"
            "(unknown/unreachable repos are reported but do not fail)."
        ),
    )
    @click.option(
        "--package",
        "-p",
        multiple=True,
        help="Specific packages to check. Default: all non-template packages.",
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.pass_context
    def audit_github_state(ctx, package, as_json):
        """Audit live GitHub state across the ecosystem (PS-172 default-branch).

        \b
        Example:
            $ scitex-dev ecosystem audit-github-state
            $ scitex-dev ecosystem audit-github-state --json
        """
        from ...._ecosystem import ECOSYSTEM, get_all_packages
        from ...._ecosystem._github_state import (
            CONVENTION_DEFAULT_BRANCH,
            audit_default_branches,
        )

        pkgs = list(package) if package else get_all_packages()
        # Templates have no published default-branch expectation.
        repos: list[tuple[str, str]] = []
        for p in pkgs:
            info = ECOSYSTEM.get(p, {})
            if info.get("category") == "template":
                continue
            repo = info.get("github_repo", "")
            if repo:
                repos.append((p, repo))

        findings = audit_default_branches(repos)

        deviating = [f for f in findings if f.deviates]
        unknown = [f for f in findings if f.unknown]

        if as_json:
            click.echo(
                json.dumps(
                    {
                        "rule": "PS-172",
                        "convention_default_branch": CONVENTION_DEFAULT_BRANCH,
                        "findings": [
                            {
                                "package": f.package,
                                "repo": f.repo,
                                "default_branch": f.default_branch,
                                "expected": f.expected,
                                "ok": f.ok,
                                "deviates": f.deviates,
                                "unknown": f.unknown,
                            }
                            for f in findings
                        ],
                        "deviating_count": len(deviating),
                        "unknown_count": len(unknown),
                    }
                )
            )
        else:
            click.echo(
                f"PS-172 default-branch convention "
                f"(expected: {CONVENTION_DEFAULT_BRANCH})"
            )
            if deviating:
                click.secho(
                    f"\n  {len(deviating)} repo(s) DEVIATE:", fg="red", bold=True
                )
                for f in deviating:
                    click.echo(
                        f"    [E] [PS-172 §gh default-branch] {f.repo}: "
                        f"default={f.default_branch!r}, expected="
                        f"{f.expected!r}. Fix: gh api -X PATCH repos/{f.repo} "
                        f"-f default_branch={f.expected}"
                    )
            if unknown:
                click.secho(
                    f"\n  {len(unknown)} repo(s) UNKNOWN (404 / unreachable):",
                    fg="yellow",
                )
                for f in unknown:
                    click.echo(f"    {f.package:28s} {f.repo}")
            ok_n = len(findings) - len(deviating) - len(unknown)
            click.echo(
                f"\n  {ok_n}/{len(findings)} conform "
                f"({len(deviating)} deviate, {len(unknown)} unknown)."
            )

        ctx.exit(1 if deviating else 0)
