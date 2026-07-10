#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `audit-mcp-tools` — companion to `audit-cli` for MCP servers."""

import click

from ....._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(ecosystem):
    @ecosystem.command(
        "audit-mcp-tools",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Check a package's MCP server against the canonical convention (warn-only).",
            description=(
                "Requires the `cli-audit` extra: pip install "
                "'scitex-dev[cli-audit]'. The package list for --all is "
                "resolved via the same registry cascade used by "
                "`audit-cli` (see that command's --help). Rules audited "
                "(per scitex `_skills/general/03_interface/03_mcp/`): "
                "§1 server registration (single FastMCP, mount pattern, "
                "no double prefix); §2 tool naming `<pkg>_<verb>_<noun>` "
                "snake_case; §3 required `mcp` subcommands (start | "
                "doctor | list-tools | show-installation); §4 `mcp "
                "list-tools` -v|-vv|-vvv + --json (behavioral); §5 "
                "`<pkg>_skills_list` and `<pkg>_skills_get` present; §6 "
                "Python-API <-> MCP-tool parity.",
            ),
            examples=(
                Example("{prog} ecosystem audit-mcp-tools scitex-hub", "One package."),
                Example(
                    "{prog} ecosystem audit-mcp-tools scitex-hub --behavioral",
                    "Include behavioral checks.",
                ),
                Example(
                    "{prog} ecosystem audit-mcp-tools --all --json > mcp-drift.json",
                    "Every registry package, as JSON.",
                ),
            ),
        ),
    )
    @click.argument("package", required=False)
    @click.option(
        "--all",
        "audit_all",
        is_flag=True,
        help="Audit every MCP-bearing package in the resolved registry.",
    )
    @click.option(
        "--behavioral",
        is_flag=True,
        help="Run subprocess-based checks (§3 mcp subcommands, §4 ladder + --json). Slow.",
    )
    @click.option(
        "--json",
        "output_json",
        is_flag=True,
        help="Machine-readable JSON output on stdout.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="With --all: list the targets that would be audited; do nothing else.",
    )
    @click.option(
        "--registry",
        "registry_path",
        default=None,
        type=click.Path(dir_okay=False),
        help="Override the registry source (highest precedence in the cascade).",
    )
    @click.option(
        "--rule",
        "rules",
        multiple=True,
        help="Only report violations of this rule (e.g. --rule §2). Repeatable.",
    )
    @click.option(
        "--exclude",
        "exclude_rules",
        multiple=True,
        help="Suppress this rule (e.g. --exclude §6). Repeatable.",
    )
    @click.option(
        "--severity",
        "min_severity",
        type=click.Choice(["info", "warn", "error"], case_sensitive=False),
        default=None,
        help="Only report violations at or above this severity.",
    )
    @click.option(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-package subprocess timeout (seconds) for behavioral checks.",
    )
    def ecosystem_audit_mcp_tools(
        package,
        audit_all,
        behavioral,
        output_json,
        dry_run,
        registry_path,
        rules,
        exclude_rules,
        min_severity,
        timeout,
    ):
        from ....audit._summary._mcp_audit import run_audit_mcp, run_audit_mcp_all

        if audit_all:
            raise SystemExit(
                run_audit_mcp_all(
                    behavioral=behavioral,
                    output_json=output_json,
                    dry_run=dry_run,
                    registry_path=registry_path,
                    rules=tuple(rules),
                    exclude=tuple(exclude_rules),
                    min_severity=min_severity,
                    timeout=timeout,
                )
            )
        if package is None:
            click.echo("error: PACKAGE is required (or pass --all)", err=True)
            raise SystemExit(2)
        raise SystemExit(
            run_audit_mcp(
                package,
                behavioral=behavioral,
                output_json=output_json,
                rules=tuple(rules),
                exclude=tuple(exclude_rules),
                min_severity=min_severity,
                timeout=timeout,
            )
        )


__all__ = ["register"]
