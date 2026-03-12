# scitex-dev

Shared developer utilities for the [SciTeX](https://scitex.ai) ecosystem.

## Overview

`scitex-dev` is a zero-dependency package providing:

- **Docs aggregation** — discover, build, and serve documentation across all scitex packages
- **Unified search** — search Python APIs, CLI commands, MCP tools, and docs with fuzzy matching
- **Version management** — track and sync versions across the ecosystem
- **Ecosystem registry** — centralized package metadata
- **Bulk rename** — safe, preview-able bulk renaming with cross-reference updates
- **Dev sync** — SSH/Git sync across development machines
- **Test runner** — local and HPC test execution
- **Dev dashboard** — Flask-based version dashboard

## Installation

```bash
pip install scitex-dev

# With Sphinx support for doc building:
pip install scitex-dev[sphinx]

# Development:
pip install scitex-dev[dev]
```

## Quick Start

### Docs Aggregation

```python
from scitex_dev.docs import get_docs, build_docs, search_docs

# All installed packages
get_docs()

# Single package
get_docs(package="scitex-writer", format="json")

# Build Sphinx docs
build_docs(package="scitex-writer")
```

### Unified Search

```python
from scitex_dev.search import search

# Search everything
search("save figure")

# With scope
search("ttest", scope="api")

# Google-like syntax
search('+required -excluded "exact phrase"')
```

### CLI (per-package mixin)

```bash
scitex-writer docs --list        # page index
scitex-writer docs --json        # structured JSON
scitex-writer docs --tldr        # quick-start summary
scitex-writer docs --page api    # specific page
```

### Version Management

```python
from scitex_dev.versions import list_versions, check_versions
versions = list_versions()
result = check_versions(["scitex", "figrecipe"])
```

## Architecture

Each ecosystem package registers itself via entry points:

```toml
# pyproject.toml
[project.entry-points."scitex_dev.docs"]
scitex-writer = "scitex_writer"
```

`scitex-dev` discovers all registered packages and provides unified access to their docs, APIs, and tools.

### Resolution Chain (docs)

1. Pre-built `_docs/` in installed package → fastest (production)
2. Sphinx `_build/` available → use existing build (dev)
3. Neither → introspect from docstrings + signatures (always works)

## License

AGPL-3.0
