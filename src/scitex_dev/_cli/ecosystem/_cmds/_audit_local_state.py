#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem audit-local-state`` — local-state convention drift.

Ecosystem-wide observe pass for the local-state-resolution standard
(`_skills/general/01_ecosystem/12_local-state-resolution.md`). For every
registered package with a local checkout it runs the deterministic
rolled-own-resolver check:

  * PS-182 — a rolled-own `_paths.py`/`paths.py` that re-implements the
    git-root / project-scope precedence instead of using
    `scitex_config._ecosystem.local_state` (the config-vs-data footgun).

PS-182 is the DEFAULT drift signal because it is deterministic and
trends to zero as packages adopt `local_state` — so the timer log stays
a crisp, actionable count rather than chronic noise. The sibling
cross-package-read rule (PS-145) is chronically non-zero during its
own warn-first bake-in, so it is OPT-IN here via
``--include-cross-package`` (it is already covered per-package by
`audit-project` / `audit-all`).

It is the command the scheduled `local-state-audit` timer runs (see
`_ecosystem_jobs._provider`); the `check_state_drift.sh` PostToolUse hook
reads that timer's log. The last stdout line is always a greppable
summary: ``LOCAL-STATE-DRIFT: <N> finding(s) across <M> package(s)``.

Sibling of `audit-registry-layout` (PS-181): both surface a local-state
rule through a small additive ecosystem command rather than folding a
global sweep into the per-repo `audit-project`/`audit-all` loop.
"""

from __future__ import annotations

import click


def register(ecosystem) -> None:
    @ecosystem.command(
        "audit-local-state",
        epilog=(
            "PS-182 (+ PS-145) — local-state convention drift across the "
            "ecosystem.\n"
            "\n"
            "Scans every registered package's local checkout for a "
            "rolled-own path resolver (PS-182). Observe-mode exit: "
            "0 = clean, 1 = drift. Add --include-cross-package to also "
            "run PS-145 (cross-package state reads). See "
            "_skills/general/01_ecosystem/12_local-state-resolution.md.\n"
            "\n"
            "Examples:\n"
            "  $ scitex-dev ecosystem audit-local-state\n"
            "  $ scitex-dev ecosystem audit-local-state --quiet\n"
            "  $ scitex-dev ecosystem audit-local-state --include-cross-package\n"
            "  $ scitex-dev ecosystem audit-local-state --json"
        ),
    )
    @click.option("--json", "json_out", is_flag=True, help="Emit JSON output.")
    @click.option(
        "--quiet",
        "-q",
        is_flag=True,
        help="Emit only the one-line LOCAL-STATE-DRIFT summary.",
    )
    @click.option(
        "--include-cross-package",
        is_flag=True,
        help=(
            "Also run PS-145 cross-package state reads (chronically noisy "
            "during its warn-first bake-in; off by default so the drift "
            "signal stays crisp)."
        ),
    )
    @click.option(
        "--severity",
        type=click.Choice(["error", "warning", "info"]),
        default="warning",
        show_default=True,
        help=(
            "Minimum severity floor. PS-182/PS-145 default to W (warn) "
            "during ecosystem adoption, so 'warning' is the useful default."
        ),
    )
    def audit_local_state(json_out, quiet, severity, include_cross_package):
        """Report local-state resolver drift (PS-182; opt-in PS-145) ecosystem-wide."""
        from ...._ecosystem._core import ECOSYSTEM, get_local_path
        from ...audit._project._check_path_resolver import (
            check_ps182_rolled_own_path_resolver,
        )
        from ...audit._project._violation import Violation

        floor = {"error": {"E"}, "warning": {"E", "W"}, "info": {"E", "W", "I"}}
        visible_set = floor.get(severity, floor["warning"])

        check_ps145 = None
        if include_cross_package:
            from ...audit._project._check_local_state import (
                check_ps145_cross_package_read,
            )

            check_ps145 = check_ps145_cross_package_read

        per_pkg: dict[str, list[Violation]] = {}
        for dist in sorted(ECOSYSTEM.keys()):
            try:
                repo = get_local_path(dist)
            except Exception:
                continue  # package has no resolvable local checkout
            if repo is None or not repo.is_dir():
                continue
            found: list[Violation] = []
            check_ps182_rolled_own_path_resolver(repo, Violation, found)
            if check_ps145 is not None:
                check_ps145(repo, dist, Violation, found)
            found = [v for v in found if v.severity in visible_set]
            if found:
                per_pkg[dist] = found

        total = sum(len(v) for v in per_pkg.values())
        n_pkgs = len(per_pkg)
        n_errors = sum(
            1 for vs in per_pkg.values() for v in vs if v.severity == "E"
        )
        exit_code = 1 if total > 0 else 0
        summary = (
            f"LOCAL-STATE-DRIFT: {total} finding(s) across {n_pkgs} package(s)"
            if total
            else "LOCAL-STATE-DRIFT: 0 findings — clean"
        )

        if json_out:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "summary": summary,
                        "total": total,
                        "packages": n_pkgs,
                        "errors": n_errors,
                        "findings": {
                            dist: [
                                {
                                    "rule": v.rule,
                                    "where": v.where,
                                    "detail": v.detail,
                                    "severity": v.severity,
                                }
                                for v in vs
                            ]
                            for dist, vs in per_pkg.items()
                        },
                        "exit_code": exit_code,
                    },
                    indent=2,
                )
            )
            raise SystemExit(exit_code)

        if not quiet:
            for dist in sorted(per_pkg):
                click.echo(f"\n### {dist} ###")
                for v in per_pkg[dist]:
                    click.echo(v.format())
        click.echo(summary)
        raise SystemExit(exit_code)


# EOF
