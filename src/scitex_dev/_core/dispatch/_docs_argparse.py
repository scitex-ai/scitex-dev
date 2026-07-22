#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``docs`` subcommand (argparse flavor) + the shared execution helpers.

``_run_docs_command`` / ``_print_page_list`` / ``_get_tldr`` are shared
with ``_docs_click.py`` (the Click flavor) -- both front-ends dispatch
into the SAME execution path so behavior never drifts between the two
CLI frameworks a downstream package might choose.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import scitex_logging as slogging

log = slogging.getLogger(__name__)


def register_docs_subcommand(
    subparsers: argparse._SubParsersAction,
    package: str,
) -> argparse.ArgumentParser:
    """Register ``docs`` with ``list`` and ``get`` verb subcommands.

    Usage::
        scitex-stats docs list            # List doc pages
        scitex-stats docs get             # Show available pages
        scitex-stats docs get api         # Show specific page
    """
    prog = package.replace("_", "-")
    parser = subparsers.add_parser(
        "docs",
        help=f"View documentation for {package}",
        description=f"Browse and query {package} documentation.",
        epilog=(
            f"Examples:\n"
            f"  {prog} docs list            # List doc pages\n"
            f"  {prog} docs list --json     # JSON output\n"
            f"  {prog} docs get             # Show available pages\n"
            f"  {prog} docs get api         # Show specific page\n"
            f"  {prog} docs get api --json  # Page as JSON\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--help-recursive",
        action="store_true",
        help="Show help for all subcommands",
    )
    docs_sub = parser.add_subparsers(dest="docs_command", title="Commands")

    # docs list
    list_p = docs_sub.add_parser(
        "list",
        help="List available documentation pages",
        epilog=(f"Examples:\n  {prog} docs list\n  {prog} docs list --json\n"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_p.add_argument("--json", action="store_true", dest="as_json")
    list_p.set_defaults(
        func=lambda args: _run_docs_command(
            argparse.Namespace(
                list_pages=True,
                page=None,
                as_json=args.as_json,
                tldr=False,
                format=None,
            ),
            package=package,
        )
    )

    # docs get [page]
    get_p = docs_sub.add_parser(
        "get",
        help="Show a documentation page",
        epilog=(
            f"Examples:\n"
            f"  {prog} docs get               # show overview\n"
            f"  {prog} docs get api           # specific page\n"
            f"  {prog} docs get api --json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    get_p.add_argument(
        "name", nargs="?", default=None, help="Page name (see 'docs list')"
    )
    get_p.add_argument("--json", action="store_true", dest="as_json")
    get_p.add_argument("--format", type=str, default=None, choices=["html", "json"])
    get_p.set_defaults(func=lambda args: _run_docs_get(args, package=package))

    # bare `docs` → show help
    def _default_handler(args):
        if getattr(args, "help_recursive", False):
            parser.print_help()
            print()
            for sub_name, sub_p in [("list", list_p), ("get", get_p)]:
                print(f"--- {sub_name} ---")
                sub_p.print_help()
                print()
            return
        if args.docs_command is None:
            parser.print_help()

    parser.set_defaults(func=_default_handler)
    return parser


def _run_docs_get(args: argparse.Namespace, package: str) -> None:
    """Handle 'docs get [name]' — show page or list available pages."""
    if args.name is None:
        ns = argparse.Namespace(
            list_pages=True,
            page=None,
            as_json=getattr(args, "as_json", False),
            tldr=False,
            format=None,
        )
    else:
        ns = argparse.Namespace(
            list_pages=False,
            page=args.name,
            as_json=getattr(args, "as_json", False),
            tldr=False,
            format=getattr(args, "format", None),
        )
    _run_docs_command(ns, package=package)


def _run_docs_command(args: argparse.Namespace, package: str) -> None:
    """Execute the docs subcommand."""
    import logging

    logging.getLogger("scitex_dev._core.discovery").setLevel(logging.ERROR)
    from ..._docs.docs import get_docs

    # --tldr: concise quick-start
    if args.tldr:
        tldr = _get_tldr(package)
        if args.as_json:
            print(json.dumps({"package": package, "tldr": tldr}))
        else:
            print(tldr)
        return

    # Determine format. Note: page listings always use the rich manifest
    # (format=None) so the text and --json paths show the same data —
    # downgrading to format="json" here would drop page titles.
    fmt = args.format
    if args.list_pages:
        fetch_fmt = None
    elif args.as_json and fmt is None:
        fetch_fmt = "json"
    else:
        fetch_fmt = fmt

    try:
        result = get_docs(package=package, format=fetch_fmt, page=args.page)
    except LookupError as e:
        log.error(str(e))
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
    from ..._docs.docs import get_docs

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


__all__ = [
    "register_docs_subcommand",
    "_run_docs_get",
    "_run_docs_command",
    "_print_page_list",
    "_get_tldr",
]
