# Selective MCP discovery and context accounting

SciTeX reuses FastMCP's `RegexSearchTransform` to defer tool definitions. It
provides a small metadata measurement helper, without a custom search engine,
tokenizer, provider ontology or agent profile system. This source capability
requires a Dev version containing `scitex_dev.context`; it is not a claim about
older installed packages or currently running SciTeX services.

## Configure an existing host

Apply the host's package selection and authorization policy first, then call
once while constructing its FastMCP server:

```python
from scitex_dev import configure_mcp_discovery

configure_mcp_discovery(server, max_results=5, always_visible=[])
```

This delegates directly to upstream `RegexSearchTransform`. Its `search_tools`
and `call_tool` interfaces defer the original tool definitions until requested.
`always_visible` retains explicitly named tools. `search=False` leaves the
existing discovery behavior in place. Missing upstream transform support fails
explicitly; there is no silent full-catalog fallback. The optional host setup
helper is not automatically applied to Dev's own server. Visibility is not an
authorization boundary or proof of handler health.

The interface uses MCP rather than a vendor-specific model API. Clients differ
in how they cache/discover tool definitions and choose search calls; configuring
a server does not measure a client's system prompt, conversation or model
window. Existing client integrations remain responsible for their own loading
and consent policy. No external installer is executed by these helpers.

## Measure a caller-selected snapshot

```bash
scitex-dev context measure --input selected-snapshot.json --json
cat selected-snapshot.json | scitex-dev context measure --json
# With an umbrella installation exposing the Dev dispatcher:
scitex dev context measure --input selected-snapshot.json --json
```

Input is a local JSON file or stdin (`--input -`); output is JSON on stdout.
The command does not crawl installed providers, import leaf handlers, retrieve
skill bodies, read conversations/credentials or write a report file. The pure
Python `measure_context(**snapshot)` and MCP `dev_context_measure` accept the
same five fields: `tools`, `skill_headers`, `instructions`, `tool_owners`, and
`skill_owners`. Invalid metadata is a visible exception/CLI error/MCP tool error.

Supply actual tool definitions advertised to the client at that observation,
not the complete installed catalog. Skill headers are caller-selected metadata
such as `name`, `description`, `namespace`, `version` and `source_hash`; known
body fields `body`, `content`, `text` and `instructions` are rejected at the
header's top level. Caller selection remains responsible for excluding full
bodies stored under other fields. No skill file is opened by measurement.

Names must be nonblank and unique within each list. Use existing registry
qualified skill identities when namespaces collide. Ownership is supplied
explicitly through the maps, never inferred from tool prefixes, header fields
or installation. Owner values must be nonblank strings; `unattributed` is a
reserved aggregate bucket. Missing ownership stays `owner: null` with
`ownership: unattributed` per item.

```json
{
  "tools": [{"name": "opaque_action", "inputSchema": {"type": "object"}}],
  "skill_headers": [{"name": "existing-qualified-guide", "description": "Header only"}],
  "tool_owners": {"opaque_action": "scitex-leaf"},
  "skill_owners": {"existing-qualified-guide": "scitex-leaf"},
  "instructions": "Selected shared instructions"
}
```

## Interpret the report

`schema_version` is `scitex-context-report/1`; `scope` is
`caller_supplied_advertised_metadata`. Input descriptions and bodies are not
reproduced. `items` reports kind, name, declared/unknown owner and sizes;
`packages` sums item counts and sizes by declared owner/unknown bucket.

`total`, item sizes and `instructions` measure compact, sorted-key JSON with
Unicode preserved, using Unicode code points (`characters`) and UTF-8 bytes.
They do not measure protocol framing or an exact wire representation.
`instructions_measurement: serialized_json_string` makes its quotes/escapes
explicit; `instructions_raw` separately measures the raw instruction string.
Owner/item sums exclude top-level framing and shared instructions, so they must
not be shown as 100% of `total` or of a model context window.

`tokens` and `tokenizer` are `null`, and `client_total_context` is `not_observed`.
No characters-per-token estimate is invented. System/developer messages,
conversation, results, loaded skill bodies and other client additions require
separate observation; installed counts must not be labeled loaded context.

The source regression fixture defines 50 inert tools plus a disabled tool. A
real in-process FastMCP client observes 50 eligible definitions before search,
two upstream discovery tools after configuration, the requested definition on
search, no disabled definition and zero business-handler calls. That is fixture
evidence, not a measurement of a SciTeX live catalog or a client token budget.
