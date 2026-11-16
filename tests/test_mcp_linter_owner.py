"""The owning Dev MCP server exposes real lint capabilities standalone."""

import asyncio
import json

from fastmcp import Client

from scitex_dev._mcp._server import mcp


def test_dev_server_lists_and_dispatches_linter_rules():
    async def exercise():
        async with Client(mcp) as client:
            names = {tool.name for tool in await client.list_tools()}
            assert {
                "dev_config_show",
                "linter_check_source",
                "linter_list_rules",
            } <= names
            result = await client.call_tool("linter_list_rules", {"category": "io"})
            assert not result.is_error
            data = json.loads(result.content[0].text)
            assert data["count"] > 0
            assert all(rule["category"] == "io" for rule in data["rules"])

    asyncio.run(exercise())
