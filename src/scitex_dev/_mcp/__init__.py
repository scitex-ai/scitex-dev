"""SciTeX-dev MCP integration: docs tool wrappers, server, and compatibility helpers.

Module map:
- `_core`    — `register_docs_tools` + `docs_list/docs_get/docs_build/docs_search`
- `_utils`   — `wrap_as_mcp`, `async_wrap_as_mcp`, `run_as_mcp`, `result_to_mcp`
- `_compat`  — `get_tools_sync` (FastMCP version-bridge helpers)
- `_server`  — top-level `mcp` FastMCP server instance
"""

from __future__ import annotations

from ._compat import get_tools_sync
from ._core import (
    docs_build,
    docs_get,
    docs_list,
    docs_search,
    register_docs_tools,
)
from ._utils import async_wrap_as_mcp, result_to_mcp, run_as_mcp, wrap_as_mcp

__all__ = [
    "async_wrap_as_mcp",
    "docs_build",
    "docs_get",
    "docs_list",
    "docs_search",
    "get_tools_sync",
    "register_docs_tools",
    "result_to_mcp",
    "run_as_mcp",
    "wrap_as_mcp",
]
