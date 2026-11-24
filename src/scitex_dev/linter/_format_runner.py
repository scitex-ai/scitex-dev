#!/usr/bin/env python3
"""Implementation of `scitex-dev lint format-files`.

Handles both ``.py`` and ``.ipynb`` so the click handler in
``cli.py`` stays small. Notebooks are dispatched through
``fixer.fix_file`` (which round-trips JSON); ``.py`` files reuse
``fix_source`` so ``--diff`` keeps working.

Returns an exit code:
- ``0`` — clean (no changes needed) or fixes applied
- ``1`` — `--check` mode found files that would be changed
- ``2`` — bad path
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

import click


def run(path: str, check: bool, diff: bool, dry_run: bool, as_json: bool) -> int:
    from ._collect import collect_files
    from .config import load_config
    from .fixer import fix_file, fix_source

    config = load_config(path)
    target = Path(path)
    rows = []

    def emit_json(error=None):
        click.echo(json.dumps({
            "path": str(target), "check": check, "dry_run": dry_run,
            "diff": diff, "files": rows,
            "summary": {
                "files": len(rows),
                "changed": sum(row["changed"] for row in rows),
                "written": sum(row["written"] for row in rows),
            },
            "error": error,
        }))

    if not target.exists():
        click.echo(f"Error: {path} not found", err=True)
        if as_json:
            emit_json(f"{path} not found")
        return 2

    files = collect_files(target, config=config)
    if not files:
        click.echo(f"No Python or notebook files found in {path}", err=True)
        if as_json:
            emit_json()
        return 0

    changed = 0
    for f in files:
        if f.suffix == ".ipynb":
            _, did_change = fix_file(
                str(f), write=not (check or dry_run), config=config
            )
            rows.append({"file": str(f), "changed": did_change,
                         "written": did_change and not (check or dry_run),
                         "diff": None})
            if did_change:
                changed += 1
                verb = "Would fix" if (check or dry_run) else "Fixed"
                if not as_json:
                    click.echo(f"{verb} {f}")
            continue

        original = f.read_text(encoding="utf-8")
        fixed = fix_source(original, filepath=str(f), config=config)
        row = {"file": str(f), "changed": fixed != original,
               "written": False, "diff": None}
        rows.append(row)
        if fixed == original:
            continue
        changed += 1
        if diff:
            d = difflib.unified_diff(
                original.splitlines(keepends=True),
                fixed.splitlines(keepends=True),
                fromfile=str(f),
                tofile=str(f),
            )
            if as_json:
                row["diff"] = "".join(d)
            else:
                sys.stdout.writelines(d)
        if check or dry_run:
            if not as_json:
                click.echo(f"Would fix {f}")
        else:
            f.write_text(fixed, encoding="utf-8")
            row["written"] = True
            if not as_json:
                click.echo(f"Fixed {f}")

    if as_json:
        emit_json()
        return 1 if check and changed else 0
    if changed == 0:
        click.echo("All files clean")
        return 0
    if check:
        click.echo(f"\n{changed} file(s) would be changed")
        return 1
    if dry_run:
        click.echo(f"\n{changed} file(s) would be fixed (dry-run)")
        return 0
    click.echo(f"\n{changed} file(s) fixed")
    return 0


# EOF
