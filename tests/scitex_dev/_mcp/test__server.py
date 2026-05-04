"""Smoke test for scitex_dev._mcp._server — top-level FastMCP instance."""

from __future__ import annotations


def test_server_module_importable():
    from scitex_dev._mcp import _server

    assert hasattr(_server, "mcp")
    assert _server.mcp.name == "scitex-dev"
