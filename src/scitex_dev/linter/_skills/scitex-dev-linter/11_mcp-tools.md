---
description: |
  [TOPIC] Linter MCP tools
  [DETAILS] Discover rules, check source and read linter skills through scitex-dev.
tags: [scitex-dev-linter-mcp-tools]
---

# Linter MCP tools

The linter engine is owned by scitex-dev. Its standalone MCP server registers
the tools below. Through the SciTeX umbrella, each name gains one `dev_` prefix,
for example `dev_linter_list_rules`.

| Standalone Dev name | Purpose |
| --- | --- |
| `linter_check` | Lint a file, filtered by severity or category |
| `linter_check_source` | Lint an in-memory Python source string |
| `linter_list_rules` | List built-in and installed plugin rules |
| `linter_skills_list` | List bundled linter skill pages |
| `linter_skills_get` | Read one linter skill; omit `name` for the overview |

Call `linter_list_rules` for current IDs, categories and severities instead of
assuming a fixed rule count. For example, `category="io"` filters I/O rules.
Pass the source text to `linter_check_source` to check a snippet without a file.

Skills use the `scitex-dev-linter` namespace registered by the scitex-dev
distribution. Discovery and reads use the shared installed-provider dispatcher;
there is no dependency on the retired scitex-linter package.
