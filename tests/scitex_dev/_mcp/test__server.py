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


def test_server_instructions_reference_registered_tools():
    # Arrange
    import asyncio
    import re

    from fastmcp import Client

    from scitex_dev._mcp._server import mcp

    async def advertised_and_registered():
        async with Client(mcp) as client:
            # Modern discover has no initialize_result; both expose real metadata.
            initialized = client.initialize_result
            instructions = (
                initialized.instructions
                if initialized is not None
                else client.instructions
            )
            tools = await client.list_tools()
            return set(re.findall(r"\b(?:dev_|mcp_docs_)[a-z0-9_]+\b", instructions)), {
                tool.name for tool in tools
            }

    # Act
    advertised, registered = asyncio.run(advertised_and_registered())

    # Assert
    assert advertised and advertised <= registered, {
        "advertised": sorted(advertised),
        "missing": sorted(advertised - registered),
    }
