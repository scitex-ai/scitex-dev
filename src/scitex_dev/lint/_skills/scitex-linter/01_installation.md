---
description: |
  [TOPIC] scitex-linter Installation
  [DETAILS] pip install scitex-linter, optional [mcp] extra; smoke verify with `scitex-linter --version`.
tags: [scitex-linter-installation]
---

# Installation

## Standard

```bash
pip install scitex-linter
```

## Optional extras

| Extra | Adds                                          |
|-------|-----------------------------------------------|
| `mcp` | fastmcp (expose linter rules to AI agents)    |
| `all` | every extra above                             |

```bash
pip install 'scitex-linter[mcp]'
```

## Verify

```bash
python -c "import scitex_linter; print(scitex_linter.__version__)"
scitex-linter --help
scitex-linter list-rules | head
```

## Optional flake8 plugin

`scitex-linter` registers a flake8 entry point (`STX`) once installed —
no extra step required.
