---
description: |
  [TOPIC] scitex-dev linter Quick Start
  [DETAILS] Smallest useful example — check a file or string for SciTeX-pattern violations.
tags: [scitex-dev-linter-quick-start]
---

# Quick Start

## Check a file from the CLI

```bash
scitex-dev linter validate-files src/
```

Each violation prints with rule code (`STX-IO001`, ...) and a
short message; exit code is non-zero when violations are found.

## Check a snippet from Python

```python
from scitex_dev import linter

# All rules grouped by category
rules = scitex_dev.linter.list_rules()
print(len(rules), "rules total")

# Filter by category
io_rules = scitex_dev.linter.list_rules(category="io")
```

The richer programmatic surface (`check_source`, `check_files`) lives
under `scitex_dev.linter._linter` and is also exposed via MCP tools.

## Auto-fix what can be auto-fixed

```bash
scitex-dev linter format-files src/
```

## Pre-commit integration

Add a hook that calls `scitex-dev linter validate-files`. See
`07_rule-catalog.md` for which rules are advisory vs blocking.

## Library directories

In source after 0.62.30, a project whose Python files are library modules can
declare its root in `pyproject.toml`:

```toml
[tool.scitex-dev.linter]
library_dirs = ["."]
```

The dot is relative to that configuration file, including when the CLI runs
from another directory. Absolute library directories match their resolved
descendants; sibling directories and symlinks targeting files outside the
configured root retain normal classification. Named entries such as `lib`
keep their existing directory-component matching behavior. The legacy
`[tool.scitex-linter]` table remains supported.

This classifies library modules for script-only checks; it does not exclude
files from linting. An unconfigured script still requires its `__main__`
guard. A directly constructed `LinterConfig(library_dirs=["."])` uses the
process's current directory instead of a configuration-file location.

The owning controls in `tests/scitex_dev/linter/test__source_helpers.py` use
real project files and CLI calls. Public package delivery is separate from
these source checks.

## Next steps

- `04_cli-reference.md` — full CLI summary
- `06_quick-start.md` — extended walkthrough
- `07_rule-catalog.md` — every built-in STX-* rule
- `10_cli-reference.md` — CLI option-level reference
- `11_mcp-tools.md` — MCP tools for AI agents
