#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem audit-registry-layout`` — PS-181.

This command is the actual entry point for PS-181 (see
``_cli/audit/_project/_check_registry_layout.py`` for the full "why a
sibling command instead of folding into `audit-project`/`audit-all`"
rationale). It scans every ``~/.scitex/<pkg>/`` state directory under
``$SCITEX_DIR`` (default ``~/.scitex``) — global scope, not tied to a
single distribution/repo — and reports drift using the same
``RULES``/``Violation`` formatting machinery as ``audit-project`` for
consistent output.
"""

from __future__ import annotations

import click


def register(ecosystem) -> None:
    @ecosystem.command(
        "audit-registry-layout",
        epilog=(
            "PS-181 — ~/.scitex/<pkg>/ registry-layout conformance.\n"
            "\n"
            "Scoped to the user's entire $SCITEX_DIR tree (every "
            "installed package's local-state dir), NOT a single repo — "
            "unlike every other PS-1xx rule. See "
            "`scitex-dev registry-normalize <pkg>` to fix mechanically "
            "(dry-run by default).\n"
            "\n"
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-registry-layout\n"
            "  $ scitex-dev ecosystem audit-registry-layout --json\n"
            "  $ scitex-dev ecosystem audit-registry-layout --scitex-dir /tmp/fake-home/.scitex"
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
            "ecosystem adoption, so 'warning' is the useful default here "
            "(unlike audit-project's 'error' default)."
        ),
    )
    def audit_registry_layout(scitex_dir_opt, json_out, severity):
        """Check every `~/.scitex/<pkg>/` state dir against the canonical layout."""
        from pathlib import Path

        from ...audit._project._check_registry_layout import check_registry_layout
        from ...audit._project._violation import Violation

        if scitex_dir_opt:
            scitex_dir = Path(scitex_dir_opt).expanduser()
        else:
            from scitex_config._ecosystem import local_state

            scitex_dir = local_state.user_root()

        violations: list[Violation] = []
        check_registry_layout(scitex_dir, Violation, violations)

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
            click.echo(f"registry-layout: no PS-181 findings under {scitex_dir}")
            raise SystemExit(exit_code)

        click.echo(f"registry-layout ({scitex_dir}): {len(visible)} finding(s)")
        for v in visible:
            click.echo(v.format())
        raise SystemExit(exit_code)


# EOF
