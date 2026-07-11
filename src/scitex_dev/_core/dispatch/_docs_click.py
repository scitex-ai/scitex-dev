#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``docs`` subcommand group (Click flavor).

Shares its execution path with ``_docs_argparse.py`` -- both dispatch
into ``_run_docs_command`` so the argparse and Click front-ends a
downstream package might choose never drift in behavior.
"""

from __future__ import annotations

import argparse

from ._docs_argparse import _run_docs_command


def docs_click_group(package: str, name: str = "docs"):  # noqa: D401
    """Create a Click command group for docs (requires Click installed).

    Usage::
        from scitex_dev.cli import docs_click_group
        cli.add_command(docs_click_group(package="scitex-writer"))
    """
    try:
        import click
    except ImportError:
        raise ImportError("Click is required for docs_click_group. pip install click")

    from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup

    @click.group(
        name=name,
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="View package documentation (list / get / search).",
            examples=(
                Example("{prog} docs list", "List doc pages."),
                Example("{prog} docs get", "Show available pages."),
                Example("{prog} docs get api", "Show a specific page."),
                Example(
                    "{prog} docs search QUERY",
                    "Search across docs/APIs/CLI/MCP.",
                ),
            ),
        ),
    )
    @click.pass_context
    def docs_grp(ctx):
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @docs_grp.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List available documentation pages.",
            examples=(
                Example("{prog} docs list", "Human-readable list."),
                Example("{prog} docs list --json", "Structured JSON."),
            ),
        ),
    )
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def docs_list(as_json):
        ns = argparse.Namespace(
            list_pages=True,
            page=None,
            as_json=as_json,
            tldr=False,
            format=None,
        )
        _run_docs_command(ns, package=package)

    @docs_grp.command(
        "get",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Show documentation. Without PAGE_NAME, shows package overview.",
            examples=(
                Example("{prog} docs get", "Show the package overview."),
                Example("{prog} docs get api", "Show a specific page."),
                Example("{prog} docs get api --format json", "Page as JSON."),
            ),
        ),
    )
    @click.argument("page_name", required=False, default=None)
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    @click.option("--format", "fmt", type=click.Choice(["html", "json"]), default=None)
    def docs_get(page_name, as_json, fmt):
        if page_name is None:
            # No page given — show available pages
            ns = argparse.Namespace(
                list_pages=True,
                page=None,
                as_json=as_json,
                tldr=False,
                format=None,
            )
        else:
            ns = argparse.Namespace(
                list_pages=False,
                page=page_name,
                as_json=as_json,
                tldr=False,
                format=fmt,
            )
        _run_docs_command(ns, package=package)

    return docs_grp


__all__ = ["docs_click_group"]
