#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable CLI mixins for ``docs`` and ``skills`` subcommands.

Each package adds subcommands with minimal boilerplate::

    # In scitex_writer/_cli/__init__.py (argparse)
    from scitex_dev.cli import register_docs_subcommand, register_skills_subcommand
    register_docs_subcommand(subparsers, package="scitex-writer")
    register_skills_subcommand(subparsers, package="scitex-writer")

    # Or with Click
    from scitex_dev.cli import docs_click_group
    cli.add_command(docs_click_group(package="scitex-writer"))
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def register_docs_subcommand(
    subparsers: argparse._SubParsersAction,
    package: str,
) -> argparse.ArgumentParser:
    """Register a ``docs`` subcommand on an argparse subparser group.

    Args:
        subparsers: The subparsers action from the parent parser.
        package: Package name this CLI belongs to.

    Returns:
        The created subparser (for further customization).
    """
    parser = subparsers.add_parser(
        "docs",
        help=f"View documentation for {package}",
        description=f"Browse and query {package} documentation.",
    )
    _add_docs_arguments(parser)
    parser.set_defaults(func=lambda args: _run_docs_command(args, package=package))
    return parser


def _add_docs_arguments(parser: argparse.ArgumentParser) -> None:
    """Add standard docs arguments to a parser."""
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_pages",
        help="List available documentation pages",
    )
    parser.add_argument(
        "--page",
        type=str,
        default=None,
        help="Show a specific documentation page",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output as structured JSON (LLM-friendly)",
    )
    parser.add_argument(
        "--tldr",
        action="store_true",
        help="Show a concise quick-start summary (< 20 lines)",
    )
    parser.add_argument(
        "--format",
        type=str,
        default=None,
        choices=["html", "json"],
        help="Documentation format to retrieve",
    )


def _run_docs_command(args: argparse.Namespace, package: str) -> None:
    """Execute the docs subcommand."""
    from .docs import get_docs

    # --tldr: concise quick-start
    if args.tldr:
        tldr = _get_tldr(package)
        if args.as_json:
            print(json.dumps({"package": package, "tldr": tldr}))
        else:
            print(tldr)
        return

    # Determine format
    fmt = args.format
    if args.as_json and fmt is None:
        fmt = "json"

    try:
        result = get_docs(package=package, format=fmt, page=args.page)
    except LookupError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    # --list: show page index
    if args.list_pages:
        _print_page_list(result, as_json=args.as_json)
        return

    # Default output
    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
    elif isinstance(result, dict):
        print(json.dumps(result, indent=2, default=str))
    elif isinstance(result, Path) and result.is_file():
        # --page returns a file path — print its content
        print(result.read_text(encoding="utf-8"))
    else:
        print(result)


def _print_page_list(result, as_json: bool = False) -> None:
    """Print a page listing from a manifest or page dict."""
    if isinstance(result, dict):
        pages = result.get("pages", [])
        if as_json:
            print(json.dumps({"pages": pages}))
        else:
            if isinstance(pages, list) and pages and isinstance(pages[0], dict):
                for p in pages:
                    print(f"  {p.get('name', '?'):20s} {p.get('title', '')}")
            elif isinstance(pages, list):
                for name in pages:
                    print(f"  {name}")
            else:
                print("  (no pages found)")
    else:
        print(result)


def _get_tldr(package: str) -> str:
    """Get a concise quick-start summary for a package.

    Tries to extract from built docs, falls back to a generic template.
    """
    from .docs import get_docs

    try:
        result = get_docs(package=package)
    except LookupError:
        return f"{package}: package not found in scitex ecosystem."

    # Try to find a quick-start section in the docs
    if isinstance(result, dict):
        description = result.get("description", "")
        version = result.get("version", "?")
        pages = result.get("pages", [])
        page_names = [p["name"] if isinstance(p, dict) else p for p in pages[:5]]

        lines = [
            f"{package} v{version}",
            description[:100] if description else "(no description)",
            "",
            f"  pip install {package}",
            f'  python -c "import {package.replace("-", "_")}"',
        ]
        if page_names:
            lines.append("")
            lines.append(f"Docs pages: {', '.join(page_names)}")

        return "\n".join(lines)

    return f"{package}: documentation available via get_docs(package='{package}')"


def docs_click_group(package: str, name: str = "docs"):
    """Create a Click command group for docs (requires Click installed).

    Usage::
        import click
        from scitex_dev.cli import docs_click_group

        @click.group()
        def cli():
            pass

        cli.add_command(docs_click_group(package="scitex-writer"))
    """
    try:
        import click
    except ImportError:
        raise ImportError("Click is required for docs_click_group. pip install click")

    @click.command(name=name)
    @click.option("--list", "list_pages", is_flag=True, help="List doc pages")
    @click.option("--page", default=None, help="Specific page")
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    @click.option("--tldr", is_flag=True, help="Quick-start summary")
    @click.option("--format", "fmt", type=click.Choice(["html", "json"]), default=None)
    def docs_cmd(list_pages, page, as_json, tldr, fmt):
        """View package documentation."""
        ns = argparse.Namespace(
            list_pages=list_pages,
            page=page,
            as_json=as_json,
            tldr=tldr,
            format=fmt,
        )
        _run_docs_command(ns, package=package)

    return docs_cmd


def skills_click_group(package: str, name: str = "skills"):
    """Create a Click command group for skills (requires Click installed).

    Usage::
        from scitex_dev.cli import skills_click_group
        cli.add_command(skills_click_group(package="scitex-app"))
    """
    try:
        import click
    except ImportError:
        raise ImportError("Click is required. pip install click")

    @click.group(name=name, invoke_without_command=True)
    @click.pass_context
    def skills_grp(ctx):
        """View package skills (workflow-oriented guides)."""
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @skills_grp.command("list")
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def skills_list(as_json):
        """List available skill pages."""
        ns = argparse.Namespace(as_json=as_json)
        _skills_list(ns, package=package)

    @skills_grp.command("get")
    @click.argument("skill_name")
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def skills_get(skill_name, as_json):
        """Show a specific skill page."""
        ns = argparse.Namespace(name=skill_name, as_json=as_json)
        _skills_get(ns, package=package)

    return skills_grp


# =============================================================================
# Skills subcommand (argparse)
# =============================================================================


def register_skills_subcommand(
    subparsers: argparse._SubParsersAction,
    package: str,
) -> argparse.ArgumentParser:
    """Register ``skills`` with ``list`` and ``get`` verb subcommands.

    Usage::
        scitex-stats skills list              # List skill pages
        scitex-stats skills get               # Show main SKILL.md
        scitex-stats skills get test-selection # Show a reference page
    """
    parser = subparsers.add_parser(
        "skills",
        help=f"View skills for {package}",
        description=f"Browse {package} skills (workflow-oriented guides).",
    )
    skills_sub = parser.add_subparsers(dest="skills_command", title="Commands")

    # skills list
    list_p = skills_sub.add_parser("list", help="List available skill pages")
    list_p.add_argument("--json", action="store_true", dest="as_json")
    list_p.set_defaults(func=lambda args: _skills_list(args, package))

    # skills get <name>
    get_p = skills_sub.add_parser("get", help="Show a skill page")
    get_p.add_argument(
        "name",
        help="Skill name from 'skills list' (e.g. SKILL, test-selection)",
    )
    get_p.add_argument("--json", action="store_true", dest="as_json")
    get_p.set_defaults(func=lambda args: _skills_get(args, package))

    # bare `skills` → show help
    parser.set_defaults(
        func=lambda args: parser.print_help() if args.skills_command is None else None
    )
    return parser


def _skills_list(args: argparse.Namespace, package: str) -> None:
    import logging

    logging.getLogger("scitex_dev._discovery").setLevel(logging.ERROR)
    from .skills import list_skills

    result = list_skills(package=package)
    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        items = result.get(package, [])
        if not items:
            print(f"No skills found for {package}.")
            return
        for s in items:
            desc = f" -- {s['description']}" if s["description"] else ""
            print(f"  {s['name']}{desc}")


def _skills_get(args: argparse.Namespace, package: str) -> None:
    import logging

    logging.getLogger("scitex_dev._discovery").setLevel(logging.ERROR)
    from .skills import get_skill

    content = get_skill(package=package, name=args.name)
    if content:
        if args.as_json:
            print(
                json.dumps({"package": package, "name": args.name, "content": content})
            )
        else:
            print(content)
    else:
        target = f"'{args.name}' in " if args.name else ""
        print(f"Skill {target}package '{package}' not found.", file=sys.stderr)
        sys.exit(2)
