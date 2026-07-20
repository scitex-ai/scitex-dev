#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recursive help-rendering helpers for the scitex-dev root CLI group.

Extracted from ``_root.py`` (which crossed the 512-line limit). These two
functions serialize / render the full command tree for ``--help-recursive``
and its ``--json`` form. They depend only on ``click`` — no back-import of
``_root`` — so ``_root`` re-exports them without a cycle.
"""

from __future__ import annotations

import click


def _command_to_dict(
    cmd: click.Command,
    parent_ctx: click.Context | None,
    info_name: str,
) -> dict:
    """Serialize one click command (and its subcommands recursively) to a dict."""
    sub_ctx = click.Context(cmd, parent=parent_ctx, info_name=info_name)
    options: list[dict] = []
    arguments: list[dict] = []
    for p in cmd.params:
        if isinstance(p, click.Argument):
            arguments.append({"name": p.name, "required": p.required})
        else:
            options.append(
                {
                    "name": p.name,
                    "opts": list(p.opts),
                    "help": getattr(p, "help", "") or "",
                    "is_flag": bool(getattr(p, "is_flag", False)),
                }
            )
    out: dict = {
        "name": info_name,
        "help": (cmd.help or "").strip(),
        "short_help": (cmd.short_help or "").strip(),
        "options": options,
        "arguments": arguments,
    }
    if isinstance(cmd, click.Group):
        commands: dict = {}
        for sub in sorted(cmd.list_commands(sub_ctx)):
            sub_cmd = cmd.get_command(sub_ctx, sub)
            if sub_cmd is None:
                continue
            commands[sub] = _command_to_dict(sub_cmd, sub_ctx, sub)
        out["commands"] = commands
    return out


def _show_recursive_help(ctx: click.Context) -> None:
    """Recursively show help for all commands. Honours ctx.obj['json']."""
    if ctx.obj and ctx.obj.get("json"):
        import json as _json

        tree = _command_to_dict(
            ctx.command, ctx.parent, ctx.info_name or "scitex-dev"
        )
        click.echo(_json.dumps(tree, indent=2))
        return

    click.echo(ctx.get_help())
    click.echo()
    group = ctx.command
    if isinstance(group, click.Group):
        for name in sorted(group.list_commands(ctx)):
            cmd = group.get_command(ctx, name)
            sub_ctx = click.Context(cmd, parent=ctx, info_name=name)
            click.echo(f"{'=' * 60}")
            click.echo(f"Command: {name}")
            click.echo(f"{'=' * 60}")
            click.echo(sub_ctx.get_help())
            click.echo()
            if isinstance(cmd, click.Group):
                for sub_name in sorted(cmd.list_commands(sub_ctx)):
                    sub_cmd = cmd.get_command(sub_ctx, sub_name)
                    sub_sub_ctx = click.Context(
                        sub_cmd, parent=sub_ctx, info_name=sub_name
                    )
                    click.echo(f"  {'─' * 56}")
                    click.echo(f"  Subcommand: {name} {sub_name}")
                    click.echo(f"  {'─' * 56}")
                    click.echo(sub_sub_ctx.get_help())
                    click.echo()
