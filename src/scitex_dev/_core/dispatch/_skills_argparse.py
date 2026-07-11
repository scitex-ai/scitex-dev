#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``skills`` subcommand (argparse flavor) + the shared execution helpers.

``_skills_list`` / ``_skills_export`` / ``_skills_get`` are shared with
``_skills_click.py`` (the Click flavor) -- both front-ends dispatch into
the SAME execution path so behavior never drifts between the two CLI
frameworks a downstream package might choose.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


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
    prog = package.replace("_", "-")
    parser = subparsers.add_parser(
        "skills",
        help=f"View skills for {package}",
        description=f"Browse {package} skills (workflow-oriented guides).",
        epilog=(
            f"Examples:\n"
            f"  {prog} skills list\n"
            f"  {prog} skills get test-selection\n"
            f"  {prog} skills export --dry-run\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--help-recursive",
        action="store_true",
        help="Show help for all subcommands",
    )
    skills_sub = parser.add_subparsers(dest="skills_command", title="Commands")

    # skills list
    list_p = skills_sub.add_parser(
        "list",
        help="List available skill pages",
        epilog=f"Examples:\n  {prog} skills list\n  {prog} skills list --json\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_p.add_argument("--json", action="store_true", dest="as_json")
    list_p.set_defaults(func=lambda args: _skills_list(args, package))

    # skills get [name]
    get_p = skills_sub.add_parser(
        "get",
        help="Show a skill page",
        epilog=(
            f"Examples:\n"
            f"  {prog} skills get                  # list available\n"
            f"  {prog} skills get test-selection   # show specific\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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
        help="Export skills to ~/.claude/skills/scitex/",
        epilog=(
            f"Examples:\n"
            f"  {prog} skills export                 # default dest\n"
            f"  {prog} skills export --dest /tmp/skills\n"
            f"  {prog} skills export --dry-run --json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    export_p.add_argument(
        "--dest",
        default=None,
        help="Exact target directory (default: ~/.claude/skills/scitex/)",
    )
    export_p.add_argument(
        "--source",
        choices=["installed", "pypi"],
        default="installed",
        help="local (installed packages) or pypi (download wheels)",
    )
    export_p.add_argument(
        "--clean",
        action="store_true",
        help="Delete package subdirs before exporting",
    )
    export_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be exported without writing",
    )
    export_p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation when overwriting destination",
    )
    export_p.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output as JSON",
    )
    export_p.set_defaults(func=lambda args: _skills_export(args, package))

    parser.set_defaults(
        func=lambda args: parser.print_help() if args.skills_command is None else None
    )
    return parser


def _skills_list(args: argparse.Namespace, package: str) -> None:
    import logging

    logging.getLogger("scitex_dev._core.discovery").setLevel(logging.ERROR)
    from .._ecosystem._skills.skills import list_skills

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

    logging.getLogger("scitex_dev._core.discovery").setLevel(logging.ERROR)
    from .._ecosystem._skills.skills import export_skills

    from .._ecosystem._skills.skills import _get_default_export_dest

    dest = (
        Path(args.dest) if getattr(args, "dest", None) else _get_default_export_dest()
    )
    source = getattr(args, "source", "installed")
    clean = getattr(args, "clean", False)
    if getattr(args, "dry_run", False):
        from .._ecosystem._skills.skills import list_skills

        result = {
            k: [e["name"] + ".md" for e in v]
            for k, v in list_skills(package=package).items()
        }
        total = sum(len(v) for v in result.values())
        if getattr(args, "as_json", False):
            print(
                json.dumps(
                    {"dest": str(dest), "source": source, "packages": result}, indent=2
                )
            )
        else:
            print(f"Would export {total} files to {dest}/ (source={source})")
            for k, v in sorted(result.items()):
                print(f"  {k}/: {len(v)} files")
        return
    exported = export_skills(dest, package=package, clean=clean, source=source)
    if not exported:
        print(f"No skills found for {package}.", file=sys.stderr)
        sys.exit(2)
    if getattr(args, "as_json", False):
        print(
            json.dumps({k: [str(f) for f in v] for k, v in exported.items()}, indent=2)
        )
    else:
        total = sum(len(v) for v in exported.values())
        print(f"Exported {total} files across {len(exported)} packages")
        for k, v in exported.items():
            print(f"  {k}: {len(v)} files")


def _skills_get(args: argparse.Namespace, package: str) -> None:
    import logging

    logging.getLogger("scitex_dev._core.discovery").setLevel(logging.ERROR)

    # No name given → show available names
    if args.name is None:
        _skills_list(argparse.Namespace(as_json=False), package)
        return

    from .._ecosystem._skills.skills import get_skill

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


__all__ = [
    "register_skills_subcommand",
    "_skills_list",
    "_skills_export",
    "_skills_get",
]
