#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manifest schema for pre-built docs.

Each package can ship a _sphinx_html/manifest.json describing its documentation:
    {
        "package": "scitex-writer",
        "version": "0.3.0",
        "pages": [
            {"name": "index", "title": "Home", "path": "index.html"},
            {"name": "api",   "title": "API Reference", "path": "api.html"},
            ...
        ],
        "formats": ["html", "json"],
        "built_at": "2026-03-13T04:00:00Z"
    }
"""

from __future__ import annotations

import json
import scitex_logging as slogging
from pathlib import Path
from typing import Any, Optional

logger = slogging.getLogger(__name__)


def _page_file(docs_dir: Path, name: str) -> Path | None:
    """Return a regular page only when its target stays in the docs directory."""
    candidate = docs_dir / name
    if candidate.is_file() and candidate.resolve().is_relative_to(docs_dir.resolve()):
        return candidate
    return None


def read_manifest(docs_dir: Path) -> Optional[dict[str, Any]]:
    """Read a regular manifest.json whose target stays in the docs directory.

    Args:
        docs_dir: Path to the _sphinx_html/ directory.

    Returns:
        Parsed manifest dict, or None if not found/invalid.
    """
    manifest_path = _page_file(docs_dir, "manifest.json")
    if manifest_path is None:
        return None
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        if not isinstance(manifest, dict):
            logger.warning("Invalid manifest at %s: expected a JSON object", manifest_path)
            return None
        return manifest
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read manifest at %s: %s", manifest_path, e)
        return None


def write_manifest(docs_dir: Path, manifest: dict[str, Any]) -> Path:
    """Write manifest.json to a docs directory.

    Args:
        docs_dir: Target directory.
        manifest: Manifest data to write.

    Returns:
        Path to the written manifest file.
    """
    docs_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = docs_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return manifest_path


def generate_manifest(
    package: str,
    docs_dir: Path,
    version: Optional[str] = None,
) -> dict[str, Any]:
    """Generate a manifest by scanning a built docs directory.

    Lists regular HTML pages and detects JSON from regular page files whose
    resolved targets stay in the docs directory. JSON is
    available when a Sphinx ``.fjson`` page or a JSON sidecar for a listed
    HTML page exists. Inventory/control metadata alone is not a page format.
    This checks asset presence, not page validity or every page's formats.

    Args:
        package: Package name (e.g. "scitex-writer").
        docs_dir: Path to the built docs directory.
        version: Optional package version string.

    Returns:
        Manifest dict ready to write.
    """
    from datetime import datetime, timezone

    pages = []
    formats = set()

    if docs_dir.is_dir():
        for html_file in sorted(docs_dir.rglob("*.html")):
            rel = html_file.relative_to(docs_dir)
            if _page_file(docs_dir, str(rel)) is None:
                continue
            name = rel.stem if rel.parent == Path(".") else str(rel.with_suffix(""))
            pages.append(
                {
                    "name": name,
                    "title": _title_from_name(name),
                    "path": str(rel),
                }
            )
            formats.add("html")

        json_pages = any(
            _page_file(docs_dir, str(path.relative_to(docs_dir))) is not None
            for path in docs_dir.rglob("*.fjson")
        )
        json_sidecars = any(
            _page_file(docs_dir, str(Path(page["path"]).with_suffix(".json")))
            is not None
            for page in pages
            if page["path"] not in {
                "manifest.html", "globalcontext.html", "searchindex.html"
            }
        )
        if json_pages or json_sidecars:
            formats.add("json")

    return {
        "package": package,
        "version": version,
        "pages": pages,
        "formats": sorted(formats),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


def _title_from_name(name: str) -> str:
    """Convert a page name to a human-readable title."""
    return name.replace("_", " ").replace("-", " ").title()
