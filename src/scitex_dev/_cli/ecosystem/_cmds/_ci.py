#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem ci why`` — read WHY a CI run is red, cheaply.

The thin CLI verb over the ecosystem CI-failure-reading primitive
(``scitex_dev.ci.why``). Reading CI *status* is one word (``failure``);
this reads the *reason* for a fraction of the log by fetching a failing
run's ``--log-failed`` ONCE and distilling it to failing test ids,
assertion lines, or a setup ``##[error]``.

``why`` resolves a PR number / run id / branch / nothing (current branch)
to the failing run(s) behind it. A target it cannot read raises loudly
(exit 2) — UNKNOWN never reads as green. Exit is tri-state: 0 green, 1
red (the reason is printed), 2 could-not-read.
"""

from __future__ import annotations

import json as _json
import sys

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup

_CI_HELP = CliHelp(
    summary="Read the ecosystem's CI — why a run is red, not just that.",
    examples=(
        Example("{prog} ecosystem ci why 712", "Distil PR 712's failing checks."),
        Example("{prog} ecosystem ci why", "The current branch's latest run."),
    ),
)

_WHY_HELP = CliHelp(
    summary="Extract the real reason a CI run is red — as cheaply as status.",
    description=(
        "TARGET is a PR number, a run id (>=8 digits), a branch name, or "
        "omitted (the current git branch's latest run). Fetches each "
        "failing run's log once and distils it to failing test ids, "
        "assertion lines, or a setup `##[error]` — a few hundred bytes, "
        "not the whole log.",
    ),
    examples=(
        Example("{prog} ecosystem ci why 712", "Explain PR 712's failing checks."),
        Example("{prog} ecosystem ci why 29446283736", "Explain one run id."),
        Example("{prog} ecosystem ci why -R owner/repo main", "A branch of a repo."),
        Example("{prog} ecosystem ci why 712 --json", "Structured output."),
    ),
    exit_codes=(
        (0, "no failing jobs found (green)"),
        (1, "failing jobs found — the distilled reason is printed"),
        (2, "could not read the run (gh missing/unauthenticated/unresolved)"),
    ),
)


def _emit_json(runs) -> None:
    click.echo(_json.dumps([r.to_dict() for r in runs], indent=2, default=str))


def _emit_human(runs) -> None:
    from ....ci.why import render_text

    blocks: list[str] = []
    for run in runs:
        head = f"run {run.run_id}"
        if run.workflow:
            head += f": {run.workflow}"
        if run.branch:
            head += f"  [{run.branch}]"
        block = [head, render_text(run)]
        if run.url:
            block.append(f"-> {run.url}")
        blocks.append("\n".join(block))
    click.echo("\n\n".join(blocks))


def register(ecosystem):
    """Wire the ``ecosystem ci`` group (verb: ``why``) onto *ecosystem*."""

    @ecosystem.group(
        "ci",
        cls=SpecGroup,
        invoke_without_command=True,
        command_categories=[("Read", ["why"])],
        help_spec=_CI_HELP,
    )
    @click.pass_context
    def ci(ctx):
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @ci.command("why", cls=SpecCommand, help_spec=_WHY_HELP)
    @click.argument("target", required=False, default="")
    @click.option("-R", "--repo", default=None, help="Target OWNER/REPO (else CWD).")
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
    def ci_why(target, repo, as_json):
        from ....ci.why import CIWhyError, explain_ci_run

        try:
            runs = explain_ci_run(target or None, repo=repo)
        except CIWhyError as exc:
            click.echo(f"ci why: {exc}", err=True)
            sys.exit(2)

        if as_json:
            _emit_json(runs)
        else:
            _emit_human(runs)

        any_failures = any(run.failures for run in runs)
        sys.exit(1 if any_failures else 0)

    return ci


__all__ = ["register"]


# EOF
