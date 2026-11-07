---
description: |
  [TOPIC] MCP behavior and agent-selection evidence
  [DETAILS] The former make_mcp_trigger_tests sketch is not implemented in Dev. Use an owned FastMCP client/server fixture for deterministic registration and handler behavior; agent tool choice and end-to-end outcomes require separate observed evaluation.
tags: [scitex-dev-agentic-test-mcp]
---

# MCP behavior and agent-selection evidence

Dev does not provide `scitex_dev._agentic_testing.make_mcp_trigger_tests`.
The earlier page was a design sketch, not a callable API. The standalone `newb`
leaf owns its current agent-evaluation instructions; inspect the installed
version before choosing a harness.

## Deterministic local control

With FastMCP installed, an in-process client can exercise the actual registration
and handler without a provider account or external server:

```python
import asyncio
import json
from fastmcp import Client, FastMCP

server = FastMCP("owned-behavior-example")

@server.tool()
def doubled(n: int) -> int:
    return n * 2

async def main() -> None:
    async with Client(server) as client:
        tools = await client.list_tools()
        print([tool.name for tool in tools])        # ['doubled']
        result = await client.call_tool("doubled", {"n": 3})
        print(result.is_error)                     # False
        print(json.loads(result.content[0].text))   # 6

asyncio.run(main())
```

This checks the local fixture's protocol surface and returned value. For a real
leaf, use its actual server, admitted operations and isolated data, then verify
errors, permissions and observable side effects as appropriate.

## Agent evaluation is separate

A passing handler control does not prove an agent selects the right tool for a
user request, supplies appropriate arguments or achieves the intended outcome.
Record the advertised tool set, selected calls, owner/version, permissions and
resulting state. Evaluate those observations against explicit task criteria.
Provider calls, messages and real data changes need their own authorized scope;
listing tools is not permission to invoke every tool.

See [31_agentic-test-skills.md](31_agentic-test-skills.md) and
[42_context-discovery.md](42_context-discovery.md). Neither page supplies a
universal vendor token count or an implemented Dev agent-judge factory.
