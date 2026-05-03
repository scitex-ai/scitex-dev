---
description: |
  [TOPIC] Interface Mcp Required Subcommands
  [DETAILS] SciTeX MCP — required `mcp` subcommands every package CLI must expose (start, doctor, list-tools, show-installation).
tags: [scitex-general-interface-mcp-required-subcommands]
---

# §3. Required MCP subcommands

Every package CLI **must** expose these `mcp` subcommands. They are the MCP-side counterpart of the Python-API introspection commands and follow the same verbosity convention as `list-python-apis`.

| Subcommand                    | Purpose                                                                  |
|-------------------------------|--------------------------------------------------------------------------|
| `<cli> mcp start`             | Launch the MCP server (stdio by default).                                 |
| `<cli> mcp doctor`            | Self-diagnose the MCP install (deps, config, registration).               |
| `<cli> mcp list-tools`        | Enumerate registered MCP tools — `-v|-vv|-vvv` and `--json` mandated.     |
| `<cli> mcp show-installation` | Print the snippet to add to a Claude Code / MCP-host config.              |

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

## `mcp show-installation`

Print the JSON snippet a user pastes into their Claude Code / MCP host config. Example:

```bash
$ scitex-io mcp show-installation
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
