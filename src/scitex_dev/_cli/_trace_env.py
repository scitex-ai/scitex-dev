#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev trace-env-vars`` — env-var provenance CLI surface.

Mirrors ``_cli/_rename.py``: a thin ``register(main)`` entry-point that
wires the command to the top-level click group; all real logic lives in
the ``scitex_dev.trace_env`` engine package.

Two modes:

- static scan (default) — every assignment site for the named var(s)
  across shell init files, direnv, tmux global env, and the current
  process environment, with WORD-BOUNDARY matching so ``FOO`` never
  matches ``FOO_BAR``.
- dynamic trace (``--trace -- CMD ...``) — run CMD under strace and
  report the first exec stage whose child env carries the var.

Secret-shaped values (``*_KEY`` / ``*_TOKEN`` / ...) are redacted in all
output. ``--json`` emits the structured envelope; ``--quiet``/``-q``
emits a one-line summary (mirrors rename-symbols).
"""

from __future__ import annotations

import json
import sys

import click


class _PassthroughCommand(click.Command):
    """Command that records the raw sub-args (incl. ``--``) at parse time.

    Click strips the first ``--`` before the callback sees it, so a
    ``NAMES... --trace -- CMD ARGS`` invocation loses the boundary
    between the traced var names and the passthrough command. Capturing
    the raw args here lets the callback split them deterministically —
    and works identically under a real CLI and under ``CliRunner``
    (which never populates ``sys.argv``).
    """

    def parse_args(self, ctx, args):  # noqa: D102 (inherited contract)
        ctx.meta["trace_env_raw_args"] = list(args)
        return super().parse_args(ctx, args)


def _split_names_command(
    tokens: tuple[str, ...], raw_args: list[str]
) -> tuple[list[str], list[str]]:
    """Split combined positionals into (names, command) on the ``--`` marker."""
    if "--" not in raw_args:
        return list(tokens), []
    command = raw_args[raw_args.index("--") + 1 :]
    names = list(tokens[: len(tokens) - len(command)]) if command else list(tokens)
    return names, command


def register(main: click.Group) -> None:
    """Attach the ``trace-env-vars`` command to the top-level click group."""

    @main.command(
        "trace-env-vars",
        cls=_PassthroughCommand,
        context_settings={
            "ignore_unknown_options": True,
            "allow_extra_args": True,
        },
    )
    @click.argument("names", nargs=-1, type=click.UNPROCESSED, required=True)
    @click.option(
        "--trace",
        "trace_cmd",
        is_flag=True,
        help="Dynamic mode: run a command (after `--`) under strace and "
        "report the first exec stage that injects the var(s).",
    )
    @click.option(
        "--no-etc",
        is_flag=True,
        help="Skip /etc/* system surfaces (scan mode).",
    )
    @click.option(
        "--no-tmux",
        is_flag=True,
        help="Skip the `tmux show-environment -g` probe (scan mode).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Output as structured JSON.")
    @click.option(
        "--quiet",
        "-q",
        is_flag=True,
        help="Emit a one-line summary instead of the full report.",
    )
    @click.pass_context
    def _trace_env_vars(ctx, names, trace_cmd, no_etc, no_tmux, as_json, quiet):
        """Trace WHERE env var(s) are defined or injected.

        \b
        Example:
            $ scitex-dev trace-env-vars SCITEX_TODO_AGENT
            $ scitex-dev trace-env-vars FOO BAR --json
            $ scitex-dev trace-env-vars FOO -q
            $ scitex-dev trace-env-vars SCITEX_TODO_AGENT --trace -- \\
                  sac agents start scitex-todo --yes
        """
        from ..trace_env import (
            format_quiet,
            format_report,
            scan_env_vars,
            trace_env_vars,
        )

        raw_args = ctx.meta.get("trace_env_raw_args", [])
        var_names, command = _split_names_command(names, raw_args)

        if trace_cmd:
            result = trace_env_vars(
                var_names, command=command, announce=not as_json
            )
        else:
            result = scan_env_vars(
                var_names,
                include_etc=not no_etc,
                include_tmux=not no_tmux,
            )

        if as_json:
            click.echo(json.dumps(result.to_dict(), indent=2, default=str))
        elif quiet:
            click.echo(format_quiet(result))
        else:
            click.echo(format_report(result))

        sys.exit(1 if result.error else 0)


# EOF
