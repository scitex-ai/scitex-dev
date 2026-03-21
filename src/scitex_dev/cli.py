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
    list_p = docs_sub.add_parser("list", help="List available documentation pages")
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
    get_p = docs_sub.add_parser("get", help="Show a documentation page")
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

    logging.getLogger("scitex_dev._discovery").setLevel(logging.ERROR)
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
        from scitex_dev.cli import docs_click_group
        cli.add_command(docs_click_group(package="scitex-writer"))
    """
    try:
        import click
    except ImportError:
        raise ImportError("Click is required for docs_click_group. pip install click")

    prog = package.replace("_", "-")

    @click.group(name=name, invoke_without_command=True)
    @click.pass_context
    def docs_grp(ctx):
        f"""View package documentation.

        \b
        Examples:
          {prog} docs list            # List doc pages
          {prog} docs get             # Show available pages
          {prog} docs get api         # Show specific page
        """
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    @docs_grp.command("list")
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def docs_list(as_json):
        """List available documentation pages."""
        ns = argparse.Namespace(
            list_pages=True,
            page=None,
            as_json=as_json,
            tldr=False,
            format=None,
        )
        _run_docs_command(ns, package=package)

    @docs_grp.command("get")
    @click.argument("page_name", required=False, default=None)
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    @click.option("--format", "fmt", type=click.Choice(["html", "json"]), default=None)
    def docs_get(page_name, as_json, fmt):
        """Show documentation. Without PAGE_NAME, shows package overview."""
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
    @click.argument("skill_name", required=False, default=None)
    @click.option("--json", "as_json", is_flag=True, help="JSON output")
    def skills_get(skill_name, as_json):
        """Show a specific skill page."""
        if skill_name is None:
            # No name given — show available skills
            ns = argparse.Namespace(as_json=as_json)
            _skills_list(ns, package=package)
            return
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
    parser.add_argument(
        "--help-recursive",
        action="store_true",
        help="Show help for all subcommands",
    )
    skills_sub = parser.add_subparsers(dest="skills_command", title="Commands")

    # skills list
    list_p = skills_sub.add_parser("list", help="List available skill pages")
    list_p.add_argument("--json", action="store_true", dest="as_json")
    list_p.set_defaults(func=lambda args: _skills_list(args, package))

    # skills get [name]
    get_p = skills_sub.add_parser("get", help="Show a skill page")
    get_p.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Skill name (see 'skills list')",
    )
    get_p.add_argument("--json", action="store_true", dest="as_json")
    get_p.set_defaults(func=lambda args: _skills_get(args, package))

    # skills export
    export_p = skills_sub.add_parser(
        "export",
        help="Export skills to Claude Code's expected location",
    )
    export_p.add_argument(
        "--level",
        choices=["personal", "project"],
        default="project",
        help="personal (~/.claude/skills/) or project (.claude/skills/)",
    )
    export_p.add_argument(
        "--target",
        default=None,
        help="Override target directory",
    )
    export_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be copied without doing it",
    )
    export_p.set_defaults(func=lambda args: _skills_export(args, package))

    # bare `skills` → show help; --help-recursive → show all subcommand help
    def _default_handler(args):
        if getattr(args, "help_recursive", False):
            parser.print_help()
            print()
            for name, sub_p in [("list", list_p), ("get", get_p), ("export", export_p)]:
                print(f"--- {name} ---")
                sub_p.print_help()
                print()
            return
        if args.skills_command is None:
            parser.print_help()

    parser.set_defaults(func=_default_handler)
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
        print(f"Available skills for {package}:\n")
        for s in items:
            desc = f"  {s['description']}" if s["description"] else ""
            print(f"  {s['name']}")
            if desc:
                print(f"    {s['description']}")
        prog = package.replace("_", "-")
        print(f"\nUsage: {prog} skills get <name>")


def _skills_export(args: argparse.Namespace, package: str) -> None:
    import logging
    import shutil

    logging.getLogger("scitex_dev._discovery").setLevel(logging.ERROR)
    from .skills import get_skill_dir

    src_dir = get_skill_dir(package)
    if src_dir is None:
        print(f"No skills found for {package}.", file=sys.stderr)
        sys.exit(2)

    # Determine target
    skill_name = package.replace("_", "-")
    if args.target:
        target = Path(args.target) / skill_name
    elif args.level == "personal":
        target = Path.home() / ".claude" / "skills" / skill_name
    else:
        target = Path(".claude") / "skills" / skill_name

    if args.dry_run:
        print(f"Would copy: {src_dir} -> {target}")
        for f in sorted(src_dir.rglob("*.md")):
            rel = f.relative_to(src_dir)
            print(f"  {rel} -> {target / rel}")
        return

    target.mkdir(parents=True, exist_ok=True)

    # Copy SKILL.md
    skill_md = src_dir / "SKILL.md"
    if skill_md.exists():
        shutil.copy2(skill_md, target / "SKILL.md")

    # Copy references/
    refs_src = src_dir / "references"
    if refs_src.is_dir():
        refs_dst = target / "references"
        if refs_dst.exists():
            shutil.rmtree(refs_dst)
        shutil.copytree(refs_src, refs_dst)

    print(f"Exported {package} skills to {target}")
    for f in sorted(target.rglob("*.md")):
        print(f"  {f.relative_to(target)}")


def _skills_get(args: argparse.Namespace, package: str) -> None:
    import logging

    logging.getLogger("scitex_dev._discovery").setLevel(logging.ERROR)

    # No name given → show available names
    if args.name is None:
        _skills_list(argparse.Namespace(as_json=False), package)
        return

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
        print(f"Skill '{args.name}' not found in {package}.", file=sys.stderr)
        print(f"Run: {package} skills list", file=sys.stderr)
        sys.exit(2)
