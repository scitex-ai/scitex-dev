#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev skills explain-self` (+ hidden deprecated `self-explain`)."""

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(skills):
    # scitex-dev#6: explicit-destination alias. `collect` is the recommended
    # command going forward because the destination is always required —
    # callers can't be surprised by a hidden default like `export`'s
    # `~/.claude/skills/scitex/`.
    @skills.command(
        "explain-self",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Have a skills-only agent explain what this package is for.",
            description=(
                "Mounts an agent with ONLY this package's skills and asks "
                "it 'what is this for / what does it solve / how do I "
                "use it?'. Each invocation spends real Anthropic API "
                "credits on your account (the mounted container uses "
                "ANTHROPIC_API_KEY, not Claude Code plan quota). Cost = "
                "4 prompts × --runs.",
            ),
            examples=(
                Example("{prog} skills explain-self scitex-io", "Default run."),
                Example(
                    "{prog} skills explain-self scitex-stats --runs 3",
                    "3 runs per prompt.",
                ),
                Example(
                    "{prog} skills explain-self scitex-io --format markdown >> README.md",
                    "README-marker-ready output.",
                ),
            ),
        ),
    )
    @click.argument("distribution")
    @click.option("--model", default="claude-haiku-4-5", help="Claude model id.")
    @click.option(
        "--runs",
        default=1,
        type=int,
        help="Runs per prompt (>1 returns lists).",
    )
    @click.option(
        "--format",
        "out_format",
        type=click.Choice(["json", "markdown"]),
        default="json",
        help="Output format. 'markdown' is README-marker-ready.",
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="(deprecated) Equivalent to --format json. Kept for back-compat.",
    )
    def skills_self_explain(distribution, model, runs, out_format, as_json):
        import json as _json

        from .._self_explain import render_markdown, self_explain

        result = self_explain(distribution, model=model, runs_per_prompt=runs)
        # --json is the legacy flag; --format takes precedence when both are set.
        effective = "json" if as_json and out_format == "json" else out_format
        if effective == "markdown":
            click.echo(render_markdown(result), nl=False)
        else:
            click.echo(_json.dumps(result, indent=2))

    # Deprecated alias for backward compatibility.
    @skills.command("self-explain", hidden=True)
    @click.argument("distribution")
    @click.option("--model", default="claude-haiku-4-5", help="Claude model id.")
    @click.option(
        "--runs", default=1, type=int, help="Runs per prompt (>1 returns lists)."
    )
    @click.option(
        "--format",
        "out_format",
        type=click.Choice(["json", "markdown"]),
        default="json",
    )
    @click.option("--json", "as_json", is_flag=True, default=False)
    @click.pass_context
    def skills_self_explain_alias(ctx, distribution, model, runs, out_format, as_json):
        """Deprecated alias for `skills explain-self`.

        \b
        Example:
            $ scitex-dev skills self-explain scitex-io
        """
        ctx.invoke(
            skills_self_explain,
            distribution=distribution,
            model=model,
            runs=runs,
            out_format=out_format,
            as_json=as_json,
        )


__all__ = ["register"]
