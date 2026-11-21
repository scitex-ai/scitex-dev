"""Smoke test for scitex_dev._mcp._server — top-level FastMCP instance."""

from __future__ import annotations

import pytest


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


@pytest.fixture(scope="module")
def linter_protocol():
    import asyncio
    import json
    from fastmcp import Client
    from scitex_dev._mcp._server import mcp

    async def exercise():
        async with Client(mcp) as client:
            names = {tool.name for tool in await client.list_tools()}
            result = await client.call_tool("linter_list_rules", {"category": "io"})
            return names, result.is_error, json.loads(result.content[0].text)

    return asyncio.run(exercise())


def test_dev_server_registers_linter_rules(linter_protocol):
    # Arrange
    names, _, _ = linter_protocol
    # Act
    required = {"dev_config_show", "linter_check_source", "linter_list_rules"}
    # Assert
    assert required <= names


def test_dev_linter_rules_call_succeeds(linter_protocol):
    # Arrange
    _, is_error, _ = linter_protocol
    # Act
    failed = is_error
    # Assert
    assert failed is False


def test_dev_linter_returns_io_rules(linter_protocol):
    # Arrange
    _, _, data = linter_protocol
    # Act
    count = data["count"]
    # Assert
    assert count > 0


def test_dev_linter_respects_category(linter_protocol):
    # Arrange
    _, _, data = linter_protocol
    # Act
    categories = {rule["category"] for rule in data["rules"]}
    # Assert
    assert categories == {"io"}
