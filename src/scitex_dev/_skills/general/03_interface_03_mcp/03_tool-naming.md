---
description: |
  [TOPIC] Interface Mcp Tool Naming
  [DETAILS] SciTeX MCP tool naming — `<pkg>_<verb>_<noun>` snake_case, mirrors the CLI subcommand tree, examples per package.
tags: [scitex-general-interface-mcp-tool-naming]
---

# §2. Tool naming — `<pkg>_<verb>_<noun>`

Every MCP tool name has the shape:

```
<pkg>_<verb>_<noun>
```

- snake_case throughout.
- `<pkg>` = the package short name (`io`, `stats`, `dev`, …). New packages add it via `safe_mount(..., namespace="<pkg>")` from `scitex._mcp_tools._compat` — the standalone source uses **bare names**. Legacy packages (`scitex-io`) bake the prefix into the source and call `safe_mount(mcp, sub_mcp)` without a namespace; this is allowed but discouraged for new code (see [02_server-registration.md](02_server-registration.md)).
- `<verb>_<noun>` mirrors the CLI subcommand tree.

## Examples (canonical)

| CLI subcommand                         | MCP tool name              |
|----------------------------------------|----------------------------|
| `scitex-io save <obj> <path>`          | `io_save`                  |
| `scitex-io list-formats`               | `io_list_formats`          |
| `scitex-io mcp list-tools`             | `io_list_tools`            |
| `scitex-stats run-test --kind ttest`   | `stats_run_test`           |
| `scitex-stats recommend-tests`         | `stats_recommend_tests`    |
| `scitex-audio speak`                   | `audio_speak`              |
| `scitex-audio list-voices`             | `audio_list_voices`        |
| `scitex-plt plot`                      | `plt_plot`                 |
| `scitex-plt compose`                   | `plt_compose`              |
| `scitex-dev bulk-rename`               | `dev_bulk_rename`          |
| `scitex-dev ecosystem list`            | `dev_ecosystem_list`       |

## Rules

- **Hyphen → underscore** when crossing from CLI to MCP. CLI `bulk-rename` → MCP `bulk_rename`.
- **Group → underscore** as well. CLI `ecosystem list` (noun group + verb) → MCP `ecosystem_list`.
- **No double-prefix.** When the bridge calls `safe_mount(... namespace="dev")`, the standalone defines `bulk_rename`; the mount adds `dev_` → final name `dev_bulk_rename`. The standalone source must NOT also define `dev_bulk_rename` directly, or you'd get `dev_dev_bulk_rename` after the mount.

## Synonym discipline

Use the **same verb the CLI uses** (`list`, `show`, `create`, …) — see CLI [§1c noun-verb catalog](../03_interface_02_cli/06_noun-verb-catalog.md). Don't introduce MCP-specific synonyms. The auditor in §7 [audit-mcp-tools.md](08_audit-mcp-tools.md) flags drift.

## Banned name shapes

- `<pkg>_<noun>` (no verb) — same anti-pattern as bare-noun CLI leaves.
- `<pkg>_<verb>` (no noun, transitive verb) — `dev_list`, `io_save_all` ✗ if no noun is implied. Use compound (`io_list_formats`).
- `<pkg>__<x>` (double underscore) — typo class.
- Any tool name not seen in the CLI tree at all — every MCP tool must trace back to a CLI subcommand (parity invariant; see [07_python-api-parity.md](07_python-api-parity.md)).
