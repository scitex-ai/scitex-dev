"""Smoke test for scitex_dev._mcp._server — top-level FastMCP instance."""

from __future__ import annotations


def test_server_module_importable_hasattr__server_mcp():
    # Arrange
    # Act
    # Assert
    from scitex_dev._mcp import _server

    assert hasattr(_server, "mcp")


def test_server_module_importable_server_mcp_name_scitex_dev():
    # Arrange
    # Act
    # Assert
    from scitex_dev._mcp import _server

    assert _server.mcp.name == "scitex-dev"
