---
description: |
  [TOPIC] Interface Mcp Skills Integration
  [DETAILS] Delegate skill discovery and reads to the shared MCP handlers,
  preserving namespace ownership and the structured result envelope.
tags: [scitex-general-interface-mcp-skills-integration]
---

# Skills integration

An enabled leaf MCP provider should expose predictable skill discovery and read
tools. Delegate to the existing public `scitex_dev.dev_mcp.handlers` adapters;
`scitex_dev.skills` is not an implemented import path.

In an existing FastMCP server, register these wrappers (replace the package
placeholder with the leaf's registered skill namespace):

```python
from scitex_dev.dev_mcp.handlers import skills_get_handler, skills_list_handler


@mcp.tool()
async def skills_list() -> str:
    """List this provider's skill pages and owning distributions."""
    return await skills_list_handler(package="scitex-<pkg>")


@mcp.tool()
async def skills_get(name: str, owner: str | None = None) -> str:
    """Read a listed page with its distribution owner."""
    return await skills_get_handler(package="scitex-<pkg>", name=name, owner=owner)
```

This is a registration fragment: the leaf supplies its existing `mcp` server.
Do not start a server merely to validate the example. Namespace mounting and
tool exposure remain subject to the host's selected providers and opt-outs.

## Payload and ownership

Both handlers return JSON **strings** produced by `wrap_as_mcp`, with the common
result envelope. They do not return a bare dictionary with a `skills` key.
The underlying list payload maps skill namespaces to lists of metadata entries.
Entries include the owning distribution, name, path, relative path, description
and installed owner version. The underlying read payload is Markdown text, or
`None` when no matching page exists; inspect the result payload before treating
an absent page as a successful read.

A skill namespace can differ from its owning distribution. Pass the listed
`owner` to the read tool so a namespace collision cannot silently select another
package. Use names from discovery instead of constructing filesystem paths.
Disabled owners are excluded by the shared registry; ambiguous namespaces are
reported rather than resolved by an arbitrary fallback.

## Evidence

- Adapters: `scitex_dev/dev_mcp/handlers.py`, `skills_list_handler` and
  `skills_get_handler`.
- Discovery and reads: `scitex_dev/_ecosystem/_skills/skills.py`.
- Actual server registration: `scitex_dev/_mcp/_server.py`.
- Controls: `tests/scitex_dev/_ecosystem/_skills/test_skills.py` and the
  installed-provider/ownership tests in that directory.

The wrapper example requires those shared handlers in the installed Dev
version. Qualify imports and actual transport metadata separately from source
examples; a shipped skill does not prove a tool is enabled in an agent session.
