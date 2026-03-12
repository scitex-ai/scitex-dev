#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP tool wrappers for docs aggregation.

These functions return JSON strings suitable for MCP tool responses.
Register them in your MCP server::

    from scitex_dev.mcp import register_docs_tools
    register_docs_tools(mcp)
"""

from __future__ import annotations

import json
from typing import Any, Optional


def docs_list() -> str:
    """List all installed SciTeX packages with documentation.

    Returns:
        JSON string with package manifest overview.
    """
    from .docs import get_docs

    try:
        result = get_docs()
        return json.dumps(
            {
                "success": True,
                "data": result,
                "next_steps": [
                    "Use docs_get(package='<name>') for specific package docs",
                    "Use docs_get(package='<name>', format='json') for structured docs",
                ],
            },
            default=str,
        )
    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": str(e),
                "next_steps": ["Check that scitex packages are installed"],
            }
        )


def docs_get(
    package: str,
    format: Optional[str] = None,
    page: Optional[str] = None,
) -> str:
    """Get documentation for a specific SciTeX package.

    Args:
        package: Package name (e.g. "scitex-writer").
        format: None for manifest, "json" for structured, "html" for path.
        page: Specific documentation page name.

    Returns:
        JSON string with documentation content.
    """
    from .docs import get_docs

    try:
        result = get_docs(package=package, format=format, page=page)
        return json.dumps(
            {
                "success": True,
                "data": result if not isinstance(result, type(None)) else None,
                "package": package,
                "format": format,
                "next_steps": _next_steps_for(result, package, format),
            },
            default=str,
        )
    except LookupError as e:
        from ._discovery import discover_packages

        available = list(discover_packages().keys())
        return json.dumps(
            {
                "success": False,
                "error": str(e),
                "available_packages": available,
                "next_steps": [
                    f"Available packages: {', '.join(available) or 'none'}",
                    "Check package is installed with scitex_dev.docs entry point",
                ],
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": str(e),
                "next_steps": ["Check error details and retry"],
            }
        )


def docs_build(
    package: Optional[str] = None,
    formats: Optional[list[str]] = None,
) -> str:
    """Build documentation from Sphinx source.

    Args:
        package: Package name. None = build all.
        formats: List of builders ("html", "json"). Default: ["html"].

    Returns:
        JSON string with build results.
    """
    from .docs import build_docs

    try:
        result = build_docs(package=package, formats=formats)
        return json.dumps(
            {
                "success": True,
                "data": result,
                "side_effects": ["file_create: Sphinx build output"],
                "next_steps": ["Use docs_get() to view the built documentation"],
            },
            default=str,
        )
    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": str(e),
                "next_steps": [
                    "Ensure Sphinx is installed: pip install scitex-dev[sphinx]",
                    "Check that the package has docs/sphinx/conf.py",
                ],
            }
        )


def docs_search(
    query: str,
    package: Optional[str] = None,
    max_results: int = 10,
) -> str:
    """Search documentation across SciTeX packages.

    Args:
        query: Search query (keyword matching).
        package: Limit search to a single package.
        max_results: Maximum results to return.

    Returns:
        JSON string with search results.
    """
    from .docs import search_docs

    try:
        results = search_docs(
            query=query,
            package=package,
            max_results=max_results,
        )
        return json.dumps(
            {
                "success": True,
                "data": results,
                "query": query,
                "count": len(results),
                "next_steps": [
                    f"docs_get(package='{r['package']}', page='{r['name']}') for details"
                    for r in results[:3]
                ],
            },
            default=str,
        )
    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": str(e),
                "next_steps": ["Check query and retry"],
            }
        )


def register_docs_tools(mcp: Any) -> None:
    """Register docs MCP tools on a FastMCP server instance.

    Args:
        mcp: A FastMCP server instance with a @mcp.tool() decorator.
    """

    @mcp.tool()
    async def mcp_docs_list() -> str:
        """List all installed SciTeX packages with documentation."""
        return docs_list()

    @mcp.tool()
    async def mcp_docs_get(
        package: str,
        format: Optional[str] = None,
        page: Optional[str] = None,
    ) -> str:
        """Get documentation for a specific SciTeX package."""
        return docs_get(package=package, format=format, page=page)

    @mcp.tool()
    async def mcp_docs_build(
        package: Optional[str] = None,
        formats: Optional[list[str]] = None,
    ) -> str:
        """Build documentation from Sphinx source."""
        return docs_build(package=package, formats=formats)

    @mcp.tool()
    async def mcp_docs_search(
        query: str,
        package: Optional[str] = None,
        max_results: int = 10,
    ) -> str:
        """Search documentation across SciTeX packages."""
        return docs_search(query=query, package=package, max_results=max_results)


def _next_steps_for(result: Any, package: str, format: Optional[str]) -> list[str]:
    """Generate contextual next_steps hints."""
    steps = []
    if format is None:
        steps.append(
            f"docs_get(package='{package}', format='json') for structured docs"
        )
        steps.append(f"docs_get(package='{package}', format='html') for HTML path")
    elif format == "json" and isinstance(result, dict) and "pages" in result:
        pages = result["pages"]
        if pages:
            steps.append(
                f"docs_get(package='{package}', format='json', page='{pages[0]}') for page content"
            )
    elif format == "html":
        steps.append("Serve the HTML directory or embed in iframe")
    return steps
