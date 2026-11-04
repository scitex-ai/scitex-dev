---
description: |
  [TOPIC] Selective MCP discovery and metadata accounting
  [DETAILS] Reuse FastMCP search/visibility and measure caller-selected tool definitions and skill headers without inventing client token totals.
tags: [scitex-dev-context-discovery]
---

# Selective discovery and context accounting

Use the existing FastMCP `RegexSearchTransform` through
`scitex_dev.configure_mcp_discovery(server, max_results=5)` after the host applies
its existing package/authorization policy. Unsupported transform support fails
explicitly. This is upstream discovery, not a replacement permission system.
The helper does not automatically configure Dev's running server.

Measure caller-selected metadata with `scitex_dev.measure_context`, MCP
`dev_context_measure`, or the standalone/umbrella CLI:

```bash
scitex-dev context measure --input selected-snapshot.json --json
scitex dev context measure --input selected-snapshot.json --json
```

The JSON input fields are `tools`, `skill_headers`, `instructions`, `tool_owners`
and `skill_owners`. Use actual advertised definitions and selected headers, not
an installed inventory or full skill bodies. No leaf import, body fetch or
conversation read occurs. Names must be unique per list; qualify skills using
existing registry identities. Ownership maps are explicit; prefixes and header
owner fields are not ownership proof. Unknown ownership stays null/unattributed.
Known body/content/text/instructions fields are rejected in skill headers.

Reports contain Unicode code-point/UTF-8 sizes of normalized JSON, not protocol
framing. `instructions` is serialized JSON-string size; `instructions_raw`
measures the raw string. Owner sums exclude framing/shared instructions. Tokens
and tokenizer stay null; client total context is not_observed. Do not turn
installed counts or character counts into a claim about loaded context/tokens.
Tool descriptions and skill content are not echoed in the report.

MCP clients vary in how they discover/cache tools; a configured server does not
prove the client's model window or prompt contents. No external installer runs.
See `docs/context-discovery.md` in the source checkout for schema and fixture
scope. This capability must exist in the installed Dev; source alone does not
prove installed or live availability.
