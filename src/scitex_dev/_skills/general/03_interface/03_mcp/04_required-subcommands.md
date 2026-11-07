---
description: |
  [TOPIC] Interface Mcp Required Subcommands
  [DETAILS] SciTeX MCP — required `mcp` subcommands every package CLI must expose (start, doctor, list-tools, install).
tags: [scitex-general-interface-mcp-required-subcommands]
---

# §3. Required MCP subcommands

Every package CLI that registers any MCP tools **must** expose **all four** of these `mcp` subcommands. Shipping only a subset (e.g. only `list-tools`, as scitex-scholar did pre-2026-05-06 — `scitex-scholar mcp start` errored with `invalid choice: 'start' (choose from 'list-tools')`) is a §3 violation: users cannot start the server, diagnose problems, or generate the install snippet.

| Subcommand                    | Required? | Purpose                                                                  |
|-------------------------------|-----------|--------------------------------------------------------------------------|
| `<cli> mcp start`             | **yes**   | Launch the MCP server (stdio by default). Without this the server cannot run. |
| `<cli> mcp doctor`            | **yes**   | Self-diagnose the MCP install (deps, config, registration).              |
| `<cli> mcp list-tools`        | **yes**   | Enumerate registered MCP tools — `-v|-vv|-vvv` and `--json` mandated.    |
| `<cli> mcp install` | **yes**   | Print the snippet to add to a Claude Code / MCP-host config.             |

## Implementation status

The four commands above are the interface contract. The previously documented
`scitex_dev._mcp_cli.attach_mcp_subcommands` helper does not exist in the current
source or public Dev 0.62.16. Do not import it or copy its former example.

Dev's own implementation is `scitex_dev/_cli/_mcp_cmds.py`, registered through
`register_mcp_commands(main)`. It is specific to Dev's server and is not a
published generic leaf adapter. A reusable adapter remains an implementation
gap: leaves must provide and qualify the four behaviors without claiming that
a shared helper already supplies them. Preserve the existing discovery and
transport contracts when adding that adapter.

## `mcp start`

- Default transport: stdio (newline-delimited JSON-RPC).
- Optional flags: `--http`, `--port`, `--host` for HTTP transport. Document in `--help`.
- Must exit 0 cleanly when stdio is closed; exit 2 on bad config.

## `mcp doctor`

- Verifies: fastmcp version, package install (importable), tool count, optional dep state.
- Output is human-readable on stderr; structured JSON on `--json`.
- Returns exit 0 if healthy, 1 on degradation, 2 on critical (cannot start).

## `mcp list-tools`

- See [05_list-tools-ladder.md](05_list-tools-ladder.md) for the verbosity ladder.

## `mcp install`

Print the JSON snippet a user pastes into their Claude Code / MCP host config. Example:

```bash
$ scitex-io mcp install
{
  "mcpServers": {
    "scitex-io": {
      "command": "scitex-io",
      "args": ["mcp", "start"]
    }
  }
}
```

- `--shell bash` / `--shell zsh` / `--shell fish` to print shell-specific install one-liners (optional).
- `--format claude-code` (default) / `--format other-host` for alternative MCP hosts.
