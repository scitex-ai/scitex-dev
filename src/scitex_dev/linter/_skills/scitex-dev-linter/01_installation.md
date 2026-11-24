---
description: |
  [TOPIC] Linter installation
  [DETAILS] Dev owns the linter. Inspect declared runtime dependencies and extras,
  verify the current interpreter, and distinguish metadata from environment acceptance.
tags: [scitex-dev-linter-installation]
---

# Installation

The linter is part of the `scitex-dev` distribution:

```bash
python -m pip install scitex-dev
```

The current source declares FastMCP as a base runtime dependency. It does not
declare an `mcp` extra. Declared extras are `dev` (development tools), `docs`
(documentation tools) and `all` (the combined toolchain). See `pyproject.toml`;
inspect the metadata of the installed version before assuming a checkout's
features are available.

```bash
python -c "import importlib.metadata as m; print(m.version('scitex-dev'))"
scitex-dev linter --version
scitex-dev linter --help
scitex-dev linter list-rules-all --json
```

For Python, `from scitex_dev import linter` binds `linter`; use
`linter.__version__`, not an unbound `scitex_dev` variable. Dev alone does not
establish availability of the separate umbrella `scitex` adapter.

A version or catalog read is scoped evidence: it does not establish a clean
base-only installation, every optional provider, a configured hook, or a live
MCP server. See [11_mcp-tools.md](11_mcp-tools.md) for tool contracts and
[04_cli-reference.md](04_cli-reference.md) for configuration limits.

Flake8 integration remains unwired in the current Dev metadata. The adapter
class `scitex_dev.linter.flake8_plugin:SciTeXFlake8Checker` exists, but no
`flake8.extension` entry point is declared by this distribution. Installing Dev
alone does not register it. Registration, a flake8 installation and an actual
plugin run still need qualification.
