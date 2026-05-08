"""Smoke tests for the linter MCP tools module.

Mirror file for ``src/scitex_dev/linter/_mcp/tools/lint.py``. The module
registers fastmcp tools at import time; this test just verifies it
imports cleanly so PS-204/PS-207 are satisfied.
"""


def test_module_imports():
    import importlib

    importlib.import_module("scitex_dev.linter._mcp.tools.lint")
