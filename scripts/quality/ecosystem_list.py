#!/usr/bin/env python3
"""Emit the SciTeX ecosystem package list as JSONL.

Usage:
    python scripts/quality/ecosystem_list.py [--filter <categories>]

Outputs one JSON object per line (JSONL), each with:
    {"name": "<pkg>", "github_repo": "<user/repo>", "category": "<cat>"}

Use --filter to limit to specific categories (comma-separated).
Defaults to: umbrella,library,external-lib (same as the auditor).

This replaces the brittle clone+regex step in quality-audit workflows
that used to parse the ecosystem registry via regex — which broke when
the file layout changed after the 0.11.0 refactor.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main() -> None:
    args = sys.argv[1:]
    categories: set[str] = set()
    i = 0
    while i < len(args):
        if args[i] == "--filter" and i + 1 < len(args):
            categories = set(args[i + 1].split(","))
            i += 2
            continue
        i += 1

    if not categories:
        categories = {"umbrella", "library", "external-lib"}

    # Locate the registry file(s).  This script lives in scripts/quality/
    # inside the scitex-dev repo.
    # Newest layout: the ECOSYSTEM table is split across two literal part
    # modules (_registry_data_1.py / _registry_data_2.py — the 512-line
    # file cap); concatenate them in order.  Fall back to the single-file
    # _registry.py layout, then to the legacy ecosystem.py for old tags.
    repo_root = Path(__file__).resolve().parents[2]
    eco_dir = repo_root / "src" / "scitex_dev" / "_ecosystem"
    parts = [eco_dir / "_registry_data_1.py", eco_dir / "_registry_data_2.py"]
    eco_new = eco_dir / "_registry.py"
    eco_old = repo_root / "src" / "scitex_dev" / "ecosystem.py"

    if all(p.is_file() for p in parts):
        sources = parts
    elif eco_new.is_file():
        sources = [eco_new]
    elif eco_old.is_file():
        sources = [eco_old]
    else:
        print("ERROR: ecosystem registry file not found", file=sys.stderr)
        sys.exit(1)

    text = "\n".join(p.read_text(encoding="utf-8") for p in sources)

    # Match entries like:
    #     "scitex-stats": {
    #         "local_path": "...",
    #         ...
    #     },
    # The key and opening brace may be on the same line (old layout) or
    # on different lines (new _registry.py layout).
    for m in re.finditer(
        r'^\s*"([\w-]+)"\s*:\s*\n?\s*(.*?)\n\s*\}',
        text, re.MULTILINE | re.DOTALL,
    ):
        name = m.group(1)
        body = m.group(2)
        gh = re.search(r'"github_repo"\s*:\s*"([^"]+)"', body)
        cat = re.search(r'"category"\s*:\s*"([^"]+)"', body)
        category = cat.group(1) if cat else "library"
        archived = re.search(r'"archived"\s*:\s*(True|False)', body)
        is_archived = archived and archived.group(1) == "True"

        if category not in categories or is_archived or not gh:
            continue

        print(json.dumps({
            "name": name,
            "github_repo": gh.group(1),
            "category": category,
        }))


if __name__ == "__main__":
    main()
