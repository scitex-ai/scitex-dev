#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `audit-cli` — noun-verb CLI convention auditor."""

import click

from ....._ecosystem.help_spec import CliHelp, Example, SpecCommand


def _registry_cascade_paragraphs() -> tuple[str, ...]:
    """Build the dynamic registry-cascade + contents block for --help.

    Best-effort: an import/collection failure yields an empty tuple
    rather than breaking `--help`.
    """
    try:
        from ....audit._summary._audit import REGISTRY_CASCADE_DOC, _load_registry
    except Exception:
        return ()
    registry, provenance = _load_registry(None)
    from collections import defaultdict

    groups: dict[str, list[str]] = defaultdict(list)
    for name, info in registry.items():
        groups[info.get("category", "uncategorized")].append(name)

    lines: list[str] = [f"Resolved registry source: {provenance}", "", "Registry contents (used by --all):"]
    for cat in sorted(groups):
        lines.append(f"  [{cat}] ({len(groups[cat])})")
        for n in sorted(groups[cat]):
            lines.append(f"    {n}")
    return (REGISTRY_CASCADE_DOC.rstrip(), "\n".join(lines))


def register(ecosystem):
    @ecosystem.command(
        "audit-cli",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Check a package's CLI against the noun-verb convention (warn-only).",
            description=(
                (
                    "Requires the `cli-audit` extra: pip install "
                    "'scitex-dev[cli-audit]'. The package list for "
                    "--all is resolved via the registry cascade shown "
                    "below.",
                )
                + _registry_cascade_paragraphs()
            ),
            examples=(
                Example("{prog} ecosystem audit-cli scitex-plt", "One package."),
                Example(
                    "{prog} ecosystem audit-cli scitex-plt --behavioral",
                    "Include subprocess-based behavioral checks.",
                ),
                Example("{prog} ecosystem audit-cli --all", "Every registry package."),
                Example(
                    "{prog} ecosystem audit-cli --all --json > drift.json",
                    "Machine-readable, all packages.",
                ),
                Example(
                    "{prog} ecosystem audit-cli --all --dry-run",
                    "List targets only.",
                ),
            ),
        ),
    )
    @click.argument("package", required=False)
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
            "matches PACKAGE — covers worktrees and CI checkouts), else "
            "the registry's local_path, else the installed package's "
            "location. `--repo` is a legacy alias. The static §2/§11 "
            "source scans are rooted here; the command-tree walk audits "
            "the installed console script. Ignored with --all."
        ),
    )
    @click.option(
        "--all",
        "audit_all",
        is_flag=True,
        help="Audit every package in the resolved registry (see epilog for the cascade).",
    )
    @click.option(
        "--behavioral",
        is_flag=True,
        help="Run subprocess-based checks (§1a -v ladder, §3 exit codes, §8 --json stdout). Slow.",
    )
    @click.option(
        "--json",
        "output_json",
        is_flag=True,
        help="Machine-readable JSON output on stdout (per §2 / §8).",
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
        help="Only report violations of this rule (e.g. --rule §1a). Repeatable.",
    )
    @click.option(
        "--exclude",
        "exclude_rules",
        multiple=True,
        help="Suppress this rule (e.g. --exclude §4). Repeatable.",
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
    @click.option(
        "--baseline",
        "baseline_path",
        is_flag=False,
        flag_value=".scitex/dev/cli-audit-baseline.yaml",
        default=None,
        type=click.Path(dir_okay=False),
        help=(
            "Ratchet mode. Bare `--baseline` uses "
            ".scitex/dev/cli-audit-baseline.yaml (cwd); pass a PATH to "
            "override. Missing file: current violation fingerprints are "
            "recorded and the run exits 0. Existing file: recorded "
            "violations are suppressed (count shown); only NEW ones "
            "fail/warn. To re-record, delete the file and re-run. The "
            "default file is honored automatically when it exists, even "
            "without this flag."
        ),
    )
    def ecosystem_audit_cli(
        package,
        repo_path,
        audit_all,
        behavioral,
        output_json,
        dry_run,
        registry_path,
        rules,
        exclude_rules,
        min_severity,
        timeout,
        baseline_path,
    ):
        from ....audit import _summary as _cli_audit

        # Deterministic target-tree resolution (operator directive
        # 2026-07-21): explicit --path > current checkout (cwd git
        # toplevel, incl. linked worktrees) > registry local_path. Shared
        # with the other per-target auditors so --path wins uniformly.
        # --all runs many packages, so tree resolution is single-target
        # only (no repo when auditing the whole registry).
        repo = None
        if not audit_all and package is not None:
            from ....audit._target_tree import resolve_target_tree
            from ....audit._summary._cli_repo_scans import surface_cli_tree

            repo, resolved_via = resolve_target_tree(package, repo_path)
            surface_cli_tree(package, repo, resolved_via, output_json)

        raise SystemExit(
            _cli_audit.audit_cli(
                package=package,
                behavioral=behavioral,
                output_json=output_json,
                audit_all=audit_all,
                dry_run=dry_run,
                registry_path=registry_path,
                rules=tuple(rules),
                exclude=tuple(exclude_rules),
                min_severity=min_severity,
                timeout=timeout,
                baseline_path=baseline_path,
                repo_root=repo,
            )
        )


__all__ = ["register"]
