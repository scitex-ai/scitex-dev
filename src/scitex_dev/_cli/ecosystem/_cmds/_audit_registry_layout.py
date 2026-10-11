#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem audit-registry-layout`` — PS-181 and PS-234.

This command is the actual entry point for PS-181 (see
``_cli/audit/_project/_check_registry_layout.py`` for the full "why a
sibling command instead of folding into `audit-project`/`audit-all`"
rationale). It scans every ``~/.scitex/<pkg>/`` state directory under
``$SCITEX_DIR`` (default ``~/.scitex``) — global scope, not tied to a
single distribution/repo — and reports drift using the same
``RULES``/``Violation`` formatting machinery as ``audit-project`` for
consistent output.
Federated ``registry_checks`` also inspect this explicit root once, including
PS-234's runtime Git-exclusion policy across every package. Configurations
remain outside ``runtime/`` so Git can share them between hosts.
"""

from __future__ import annotations

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(ecosystem) -> None:
    @ecosystem.command(
        "audit-registry-layout",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Check package registry layout and host runtime Git exclusions.",
            description=(
                "PS-181 checks layout across the entire $SCITEX_DIR tree; "
                "PS-234 checks that every package's runtime/ state is "
                "gitignored and absent from the Git index. Shared "
                "configuration stays outside runtime/. Registered host "
                "checks run once for this root, separately from project audits. "
                "Use `registry-normalize <pkg>` for layout changes "
                "(dry-run by default). For PS-234, add a catch-all "
                "runtime/.gitignore and remove runtime entries from the "
                "Git index while retaining local files.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem audit-registry-layout",
                    "Scan the default $SCITEX_DIR.",
                ),
                Example(
                    "{prog} ecosystem audit-registry-layout --json",
                    "Structured JSON output.",
                ),
                Example(
                    "{prog} ecosystem audit-registry-layout --scitex-dir /tmp/fake-home/.scitex",
                    "Scan an alternate root.",
                ),
            ),
        ),
    )
    @click.option(
        "--scitex-dir",
        "scitex_dir_opt",
        type=click.Path(file_okay=False, dir_okay=True),
        default=None,
        help="Override $SCITEX_DIR (defaults to the resolved user root, ~/.scitex).",
    )
    @click.option("--json", "json_out", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--severity",
        type=click.Choice(["error", "warning", "info"]),
        default="warning",
        show_default=True,
        help=(
            "Minimum severity floor. PS-181 defaults to W (warn) during "
            "ecosystem adoption; PS-234 runtime-policy violations are E "
            "(errors). 'warning' reports both and is the default here "
            "(unlike audit-project's 'error' default)."
        ),
    )
    def audit_registry_layout(scitex_dir_opt, json_out, severity):
        from pathlib import Path

        from ...audit._project._check_registry_layout import check_registry_layout
        from ...audit._project._plugins import load_plugins
        from ...audit._project._violation import Violation

        if scitex_dir_opt:
            scitex_dir = Path(scitex_dir_opt).expanduser()
        else:
            from scitex_config._ecosystem import local_state

            scitex_dir = local_state.user_root()

        violations: list[Violation] = []
        check_registry_layout(scitex_dir, Violation, violations)
        for check in load_plugins().registry_checks:
            check(scitex_dir, Violation, violations)

        floor = {"error": {"E"}, "warning": {"E", "W"}, "info": {"E", "W", "I"}}
        visible_set = floor.get(severity, floor["warning"])
        visible = [v for v in violations if v.severity in visible_set]
        n_errors = sum(1 for v in violations if v.severity == "E")
        exit_code = 1 if n_errors > 0 else 0

        if json_out:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "scitex_dir": str(scitex_dir),
                        "violations": [
                            {
                                "rule": v.rule,
                                "where": v.where,
                                "detail": v.detail,
                                "severity": v.severity,
                            }
                            for v in visible
                        ],
                        "exit_code": exit_code,
                        "errors": n_errors,
                    },
                    indent=2,
                )
            )
            raise SystemExit(exit_code)

        if not visible:
            click.echo(
                f"registry-layout: no PS-181 or PS-234 findings under {scitex_dir}"
            )
            raise SystemExit(exit_code)

        click.echo(f"registry-layout ({scitex_dir}): {len(visible)} finding(s)")
        for v in visible:
            click.echo(v.format())
        raise SystemExit(exit_code)


# EOF
