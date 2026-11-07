---
description: |
  [TOPIC] MCP server registration
  [DETAILS] Leaf-owned tool registration and dispatcher-selected exposure. Use actual installed provider declarations, preserve handler identity and distinguish server construction, client discovery and observed calls. Do not duplicate leaf tool catalogs or disguise broken imports as absent packages.
tags: [scitex-general-interface-mcp-server-registration]
---

# MCP registration and ownership

Each public tool needs an authoritative registration path in its owning leaf.
The leaf defines domain behavior, parameters, descriptions and error/side-effect
contracts. A dispatcher selects installed providers and applies operator policy;
it should not maintain a second hand-written copy of every leaf tool signature.

## A concrete leaf server

With FastMCP installed, this defines a local server and registers one tool:

```python
from fastmcp import FastMCP

mcp = FastMCP("owned-example", instructions="Deterministic example arithmetic.")

@mcp.tool()
def doubled(n: int) -> int:
    return n * 2
```

The module path is owned by the leaf: `_mcp_server.py`, `_mcp/_server.py` and a
factory are different possible layouts, not interchangeable import conventions.
Inspect the actual installed declaration instead of guessing a filename.

## Dispatcher boundary

Use the installed dispatcher's provider discovery and configuration. A provider
can be installed yet disabled, ambiguous, unsupported or unreachable. Do not
silently replace it with another checkout or advertise every installed handler
without applying the selected exposure policy.

For the umbrella, inspect the current command surfaces first:

```bash
scitex mcp --help
scitex dev mcp --help
```

Module paths, namespace composition and mounting adapters vary by installed
version. Existing Root bridges use their `_mcp_tools/_compat.py` helper where
applicable; that private helper is not a universal API every leaf must import.
A configured upstream transport/proxy can preserve leaf ownership without
importing its handlers into the dispatcher.

Handle missing providers and broken providers distinctly. A declared package
whose internal import fails is not necessarily absent. Surface the actual
failure or typed availability result; do not catch every `ImportError` and
replace a broken installation with a misleading install stub.

## Verify the observed surface

- Inspect actual client tool discovery, including names and schemas.
- Check namespace composition for accidental double prefixes or collisions.
- Exercise admitted handlers with owned fixtures and verify their outcomes.
- Check disabled/unavailable providers and permission refusals explicitly.

Source registration alone proves neither client visibility nor execution.
Tool-search transforms reduce advertised metadata; they do not grant permissions.
The runnable local client example in
[32_agentic-test-mcp.md](../../../scitex-dev/32_agentic-test-mcp.md) illustrates
protocol checks without a paid model call.
