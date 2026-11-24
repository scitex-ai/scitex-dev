---
name: scitex-dev-linter
description: |
  [TOPIC] SciTeX linter
  [DETAILS] Inspect installed rule providers and validate Python with the CLI,
  Python checker functions or configured MCP tools. Rule availability and skipped
  coverage depend on the current environment; do not assume a fixed catalog.
  [WHEN] Checking SciTeX conventions, rule ownership or linter configuration.
  [HOW] Use `scitex-dev linter validate-files PATH`; use `list_rules` from
  `scitex_dev.linter` for the Python catalog. Verify hook and MCP host setup
  separately from source or skill availability.
tags: [scitex-dev-linter]
allowed-tools: mcp__scitex__linter_*
primary_interface: cli
interfaces:
  python: 1
  cli: 2
  mcp: 1
  skills: 2
  http: 0
---

# SciTeX linter

The engine dispatches installed leaf-owned rules and enforces shared scopes,
capabilities and mandatory providers. A catalog is not proof that every rule ran.
Inspect skipped coverage and errors in the actual validation result.

## Python and CLI

```python
from scitex_dev.linter import list_rules

rules = list_rules()
print(len(rules))
```

The module does not expose `check`, `check_source` or `check_files` at its top
level. See [03_python-api.md](03_python-api.md) for the actual checker modules.
Installing Dev does not establish umbrella `scitex.linter` availability; that
separate adapter and installation need their own checks.

```bash
scitex-dev linter validate-files /owned/project/tool.py --json
scitex-dev linter list-rules --json
```

Use the intended owned path and inspect the result. No hook is enabled merely
because this skill is discoverable. See [11_mcp-tools.md](11_mcp-tools.md) for
in-process tool contracts; a client still needs a configured server.

## Guides

- [01_installation.md](01_installation.md) — installation guidance
- [02_quick-start.md](02_quick-start.md) — validation and library classification
- [03_python-api.md](03_python-api.md) — Python catalog and checker calls
- [04_cli-reference.md](04_cli-reference.md) — CLI and configuration limits
- [20_env-vars.md](20_env-vars.md) — actual environment readers and gaps
- [11_mcp-tools.md](11_mcp-tools.md) — MCP tool contracts

The older detail pages [06_quick-start.md](06_quick-start.md),
[07_rule-catalog.md](07_rule-catalog.md) and
[10_cli-reference.md](10_cli-reference.md) contain historical material.
Use current installed help and rule discovery to resolve command names and
catalog availability; fixed rule counts are not coverage evidence.
