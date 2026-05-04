"""Public ecosystem-glue API — stable for other SciTeX packages.

Underscore-private modules under `scitex_dev._ecosystem.*` are
implementation; this module is the supported import path for code
in other packages (e.g. the `scitex` umbrella's MCP tools).
"""

from __future__ import annotations

from ._ecosystem._mcp._compat import get_tools_sync
from ._ecosystem._mcp._core import (
    docs_build,
    docs_get,
    docs_list,
    docs_search,
    register_docs_tools,
)
from ._ecosystem._mcp._utils import (
    async_wrap_as_mcp,
    result_to_mcp,
    run_as_mcp,
    wrap_as_mcp,
)

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
