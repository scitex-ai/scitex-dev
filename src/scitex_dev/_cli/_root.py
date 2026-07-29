#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main CLI entry point for scitex-dev."""

import json

# click is a HARD core dep (PS-213 console-script-deps-must-be-core).
# scitex-dev's [project.scripts] entry-point IS a click group, so click
# being unavailable is a CI failure, not a runtime fallback.
import click

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

# The canonical seven help categories (§4a 10a_command-categories.md):
# fixed names + order ecosystem-wide. Names below MUST match the actual
# registered command names; anything not listed falls through to the
# "Other" section in --help, which must be empty at audit-clean.
COMMAND_CATEGORIES = [
    (
        "Core",
        [
            "ecosystem",
            "ci",
            "linter",
            "gate",
            "hooks",
            "creds",
            "rename-symbols",
            "trace-env-vars",
            "registry-normalize",
            "icons",
            "host",
        ],
    ),
    # `gui` renders under Service per §4a 10a_command-categories.md.
    ("Service", ["gui", "mcp", "service", "cron"]),
    ("Diagnostics", ["doctor"]),
    ("Introspection", ["docs", "skills", "list-python-apis", "show-config"]),
    ("Shell", ["install-shell-completion", "print-shell-completion"]),
]

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup

# Spec-built help (§4 10_help-format.md, slice 3): help text is DATA —
# validated at import time, rendered uniformly. `{prog}` resolves to the
# actual invocation path at --help time (`scitex-dev` standalone,
# `scitex dev` under the umbrella passthrough).
ROOT_HELP_SPEC = CliHelp(
    summary="Shared developer utilities for the SciTeX ecosystem.",
    version_of="scitex-dev",
    examples=(
        Example("{prog} ecosystem list --json", "List ecosystem packages as JSON."),
        Example("{prog} doctor", "Diagnose ecosystem health."),
        Example("{prog} mcp start", "Start the MCP server."),
    ),
    config_resolution=(
        "config.yaml → $SCITEX_DEV_CONFIG → ~/.scitex/dev/config.yaml → defaults",
    ),
    see_also=("{prog} docs — browse doctrine and package documentation",),
)

# Recursive help-rendering helpers extracted to keep this file under the
# 512-line limit. Re-exported so `from ..._root import _show_recursive_help`
# (and `_command_to_dict`) keep resolving for existing callers/tests.
from ._root_help import _command_to_dict, _show_recursive_help

def _get_version() -> str:
    # Delegates so `--version` cannot report a bare number when TWO
    # dist-infos claim the package — see `_root_version` for the measured
    # case where this printed 0.38.0 (the OLDER of two) with no marker.
    from ._root_version import resolve_version

    return resolve_version()

# Disable Click's auto --help on THIS group only (parameter, not
# context — does not propagate to subcommands). Then re-add --help /
# -h explicitly via @click.help_option in the desired display slot so
# --help-recursive immediately follows --help.
@click.group(
    cls=SpecGroup,
    help_spec=ROOT_HELP_SPEC,
    command_categories=COMMAND_CATEGORIES,
    invoke_without_command=True,
    context_settings=CONTEXT_SETTINGS,
    add_help_option=False,
)
@click.option("--version", "-V", is_flag=True, help="Show version and exit.")
@click.help_option("-h", "--help")
@click.option("--help-recursive", is_flag=True, help="Show help for all commands.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit structured JSON output (propagates to subcommands that honour it).",
)
@click.pass_context
def main(
    ctx: click.Context,
    version: bool,
    help_recursive: bool,
    as_json: bool,
) -> None:
    # Help text lives in ROOT_HELP_SPEC (spec-built, doctrine §4) — the
    # rendered summary line carries the live version via version_of.
    # Expose the root-level --json flag to subcommands via ctx.obj so
    # commands that already honour `--json` can read the inherited
    # setting and default to structured output without the user
    # repeating the flag at each level.
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json

    if version:
        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "name": "scitex-dev",
                        "version": _get_version(),
                    }
                )
            )
        else:
            click.echo(f"scitex-dev {_get_version()}")
        ctx.exit(0)

    if help_recursive:
        _show_recursive_help(ctx)
        ctx.exit(0)

    # Version-staleness guard: warn — or hard-fail when the severity knob is
    # `error` — if this scitex-dev install is BEHIND its remote (editable) or
    # the latest published version (wheel). Placed after the --version /
    # --help-recursive short-circuits so a version/help query never trips it;
    # shell-completion and repeat invocations are guarded inside emit_if_drift.
    # An error-severity abort raises SystemExit and MUST propagate; any other
    # internal fault is swallowed so the check can never break the host CLI.
    import os as _os

    # Suppress the drift emission inside a pytest run: this guard fires on
    # EVERY CLI invocation, so when unrelated tests invoke the `scitex-dev`
    # CLI it would print a drift line into their captured output whenever the
    # test checkout is behind its remote — polluting assertions across suites
    # (seen on the self-hosted runner). Direct unit tests of check() /
    # emit_if_drift bypass main() and are unaffected.
    if not _os.environ.get("PYTEST_CURRENT_TEST"):
        from scitex_dev._release.check_editable_drift import emit_if_drift

        try:
            emit_if_drift()
        except SystemExit:
            raise
        except Exception:  # noqa: BLE001 — staleness check must never break the CLI
            pass

        # CURRENCY-gate integrity self-check (operator directive 2026-07-21):
        # catch a broken scitex-dev install itself (ambiguous dist-info /
        # RECORD-listed files missing on disk — the venv-corruption incident
        # where every version probe lied). Integrity half only — freshness is
        # already covered by emit_if_drift() above (which owns the once-per-
        # process/subprocess suppression) — at WARN so the CLI keeps working.
        try:
            from scitex_dev.staleness import ensure_current

            ensure_current(
                "scitex-dev", severity="warn", _halves=("integrity",)
            )
        except Exception:  # noqa: BLE001 — self-check must never break the CLI
            pass

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

# -------------------------------------------------------------------
# Ecosystem commands
# -------------------------------------------------------------------

from ._doctor import register_doctor_command

register_doctor_command(main)

from ._icons import register_icons_command

register_icons_command(main)

from .ecosystem._registry import register_ecosystem_commands

ecosystem_group = register_ecosystem_commands(main)

# `gui` — canonical §12 group. Wired here, not in the ecosystem
# registry, because its Phase W aliases need BOTH groups to exist:
# `ecosystem dashboard` / `start-dashboard` forward onto `gui`.
from .gui import register as _register_gui

gui_group = _register_gui(main)

# Stats now lives under `ecosystem` per noun-verb hierarchy. The legacy
# top-level `show-stats` is kept as a hidden deprecation alias for one
# cycle; remove in 0.11.0.
from ._stats import register_stats_command

register_stats_command(ecosystem_group, main_group=main)

# Quality audits — each one keeps its own command (separation of concern).
# Move them under `ecosystem` so `ecosystem audit-*` is the single
# canonical audit namespace. The top-level `quality` group is dropped;
# individual `quality audit-*` callers must update.
from .quality import _check as _cli_quality

# These sub-rules belong inside their canonical owner per the
# consolidation plan. Hidden until folded in (PR-by-PR) so the public
# surface is just five audit-* commands. Removed in 0.11.0.
#   audit-docs   → splits across audit-python-apis (README API drift)
#                  and audit-skills (SKILL.md code-example drift)
#   audit-scope  → folds into audit-project (test-import boundary)
#   audit-lines  → folds into audit-project (LOC-limits, source metric)
#   audit-frontmatter → DROPPED (frontmatter shape lives in audit-skills)
@ecosystem_group.command("audit-docs", hidden=True)
@click.option("--projects-root", default=None)
def _ecosystem_audit_docs(projects_root):
    """(deprecated) Splits into `audit-python-apis` (README API drift) and `audit-skills` (SKILL.md drift). Removed in 0.11.0."""
    raise SystemExit(_cli_quality.audit_docs(projects_root=projects_root))

@ecosystem_group.command("audit-scope", hidden=True)
@click.option("--projects-root", default=None)
def _ecosystem_audit_scope(projects_root):
    """(deprecated) Folds into `audit-project`. Removed in 0.11.0."""
    raise SystemExit(_cli_quality.audit_scope(projects_root=projects_root))

@ecosystem_group.command("audit-lines", hidden=True)
def _ecosystem_audit_lines():
    """(deprecated) Folds into `audit-project` (LOC-limits). Removed in 0.11.0."""
    raise SystemExit(_cli_quality.audit_lines())

# Umbrella-only pin freshness audit. Designed to fire from the
# umbrella package's CI; on any other package it exits 0, so it's
# safe to wire into a shared CI step.
from .audit._umbrella_pins import cli as _umbrella_pins_cli

ecosystem_group.add_command(_umbrella_pins_cli, name="audit-umbrella-pins")

# ----- Deprecation shim: `scitex-dev quality <cmd>` → ecosystem -----
# Shared 3-phase-ladder helper (02_cli/11_deprecation.md, slice 2 of the
# CLI-standardization plan). Warn phase forwards; error phase exits 2.
from .._ecosystem.click_compat import deprecated_alias

@main.group("quality", hidden=True)
def _quality_deprecated():
    """(deprecated) Use `scitex-dev ecosystem audit-*` instead."""

for _quality_cmd, _quality_target in (
    ("audit-docs", _ecosystem_audit_docs),
    ("audit-scope", _ecosystem_audit_scope),
    ("audit-lines", _ecosystem_audit_lines),
):
    deprecated_alias(
        _quality_deprecated,
        _quality_cmd,
        target=_quality_target,
        target_name=f"ecosystem {_quality_cmd}",
        remove_in="0.11",
        phase="warn",
    )

# `quality audit-frontmatter` has no forwarding target (the rule was
# DROPPED — frontmatter shape lives in audit-skills), so it sits on the
# error rung pointing at the canonical owner. Exit code 2, as before.
deprecated_alias(
    _quality_deprecated,
    "audit-frontmatter",
    target="audit-skills",
    target_name="ecosystem audit-skills",
    remove_in="0.11",
    phase="error",
)

# -------------------------------------------------------------------
# Development commands
# -------------------------------------------------------------------

# `config` → `show-config` rename, error rung of the deprecation ladder.
deprecated_alias(
    main, "config", target="show-config", remove_in="0.11", phase="error"
)

@main.command(
    "show-config",
    cls=SpecCommand,
    help_spec=CliHelp(
        summary="Show the resolved scitex-dev configuration.",
        description=(
            "Prints packages, hosts, GitHub remotes, and branches from the "
            "resolved config (see the root help for the resolution chain).",
        ),
        examples=(
            Example("{prog} show-config", "Human-readable sections."),
            Example("{prog} show-config --json", "Structured JSON output."),
        ),
    ),
)
@click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
def config_cmd(as_json):
    from .. import config_to_dict, load_config

    cfg = config_to_dict(load_config())

    if as_json:
        click.echo(json.dumps(cfg, indent=2, default=str))
        return

    # Human-readable text output: section headers + tabular rows
    sections = [
        ("Packages", "packages", ["name", "github_repo", "local_path"]),
        ("Hosts", "hosts", None),
        ("GitHub Remotes", "github_remotes", None),
        ("Branches", "branches", None),
    ]
    for title, key, cols in sections:
        items = cfg.get(key, [])
        if not items:
            continue
        click.echo(f"\n{title} ({len(items)})")
        click.echo("=" * (len(title) + 4 + len(str(len(items)))))
        for item in items:
            if isinstance(item, dict) and cols:
                parts = [str(item.get(c, "")) for c in cols]
                click.echo(
                    "  "
                    + "  ".join(
                        f"{p:25s}" if i == 0 else p for i, p in enumerate(parts)
                    )
                )
            elif isinstance(item, dict):
                click.echo("  " + " | ".join(f"{k}={v}" for k, v in item.items()))
            else:
                click.echo(f"  {item}")

# rename-symbols + the hidden `rename` deprecation alias live in
# _cli/_rename.py. Extracted to keep _root.py under the line budget
# and to give the bulk-rename surface a focused module to grow into.
from ._rename import register as _register_rename

_register_rename(main)

# trace-env-vars — env-var provenance diagnostic. Thin CLI in
# _cli/_trace_env.py; engine in scitex_dev/trace_env/ (mirrors the
# rename-symbols CLI/engine split).
from ._trace_env import register as _register_trace_env

_register_trace_env(main)

# registry-normalize — mechanical fix for PS-181 (~/.scitex/<pkg>/
# registry-layout drift). Thin CLI in _cli/_registry_normalize.py;
# engine in scitex_dev/registry_normalize/ (mirrors the rename-symbols /
# trace-env-vars CLI/engine split; shares detection logic with the
# PS-181 audit rule via registry_normalize/scan.py).
from ._registry_normalize import register as _register_registry_normalize

_register_registry_normalize(main)

# -------------------------------------------------------------------
# Documentation commands
# -------------------------------------------------------------------

from .._core.dispatch import docs_click_group

docs_grp = docs_click_group(package="scitex-dev")
main.add_command(docs_grp)

# `docs search` — canonical home for ecosystem-wide search across APIs,
# CLI, MCP tools, and documentation. The legacy top-level `search-docs`
# is kept as a hidden deprecation alias (see below). Removed in 0.11.0.
@docs_grp.command(
    "search",
    cls=SpecCommand,
    help_spec=CliHelp(
        summary="Search across APIs, CLI, MCP tools, and documentation.",
        examples=(
            Example('{prog} docs search "save figure"', "Full-text search everywhere."),
            Example("{prog} docs search version --scope api", "Limit to the API scope."),
            Example("{prog} docs search hpc --max-results 20 --json", "More hits, as JSON."),
        ),
    ),
)
@click.argument("query")
@click.option(
    "--scope", default="all", help="Search scope: all, api, cli, mcp, docs."
)
@click.option("--max-results", default=10, help="Maximum results.")
@click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
def _docs_search(query, scope, max_results, as_json):
    from .. import search as do_search
    from ._utils import wrap_as_cli

    wrap_as_cli(
        do_search,
        as_json=as_json,
        query=query,
        scope=scope,
        max_results=max_results,
    )

from .skills._manage import register_skills_commands

register_skills_commands(main)

from ._completion import register_completion_command

register_completion_command(main)

# `search` → `docs search` walked the ladder in two renames: the direct
# alias is already on the error rung; `search-docs` still forwards
# (warn rung) so existing callers keep working until v0.11.
deprecated_alias(
    main,
    "search",
    target="search-docs",
    remove_in="0.11",
    phase="error",
)

deprecated_alias(
    main,
    "search-docs",
    target=_docs_search,
    target_name="docs search",
    remove_in="0.11",
    phase="warn",
)

# -------------------------------------------------------------------
# Integration commands
# -------------------------------------------------------------------

from ._integrations import register_integration_commands

register_integration_commands(main)

# -------------------------------------------------------------------
# ci runner — self-hosted GitHub Actions runner lifecycle
# -------------------------------------------------------------------

from ..ci.runner import register_ci_runner_commands

register_ci_runner_commands(main)

# -------------------------------------------------------------------
# linter — engine moved here from scitex-linter (soft migration)
# `linter` is a noun per the noun-verb CLI convention (audit-cli §1).
# -------------------------------------------------------------------

try:
    from ..linter.cli import main_group as _linter_group

    _linter_group.name = "linter"
    _linter_group.short_help = (
        "AST-based linter (was scitex-linter). Plugins register rules "
        "via entry-point group `scitex_dev.linter.plugins` "
        "(legacy `scitex_linter.plugins` still honoured)."
    )
    main.add_command(_linter_group)
except Exception:
    pass

# -------------------------------------------------------------------
# list-python-apis
# -------------------------------------------------------------------

from ._list_apis import register_list_python_apis_command

register_list_python_apis_command(main)

# -------------------------------------------------------------------
# gate — submission-gate plugin federation (scitex_dev.gate.checks).
# Leaves register per-package pre/post-submission checks; the hook calls
# ONLY `scitex-dev gate`, staying package-agnostic (SOC).
# -------------------------------------------------------------------

from .gate import register_gate_command

register_gate_command(main)
