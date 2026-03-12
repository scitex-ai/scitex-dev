# SciTeX Dev (`scitex-dev`)

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/scitex-logo-blue-cropped.png" alt="SciTeX" width="400">
  </a>
</p>

<p align="center"><b>Shared developer utilities for the SciTeX ecosystem</b></p>

<p align="center">
  <a href="https://badge.fury.io/py/scitex-dev"><img src="https://badge.fury.io/py/scitex-dev.svg" alt="PyPI version"></a>
  <a href="https://scitex-dev.readthedocs.io/"><img src="https://readthedocs.org/projects/scitex-dev/badge/?version=latest" alt="Documentation"></a>
  <a href="https://github.com/ywatanabe1989/scitex-dev/actions/workflows/test.yml"><img src="https://github.com/ywatanabe1989/scitex-dev/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://www.gnu.org/licenses/agpl-3.0"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg" alt="License: AGPL-3.0"></a>
</p>

<p align="center">
  <a href="https://scitex-dev.readthedocs.io/">Full Documentation</a> · <code>pip install scitex-dev</code>
</p>

---

## Problem

The SciTeX ecosystem spans multiple packages (scitex-clew, scitex-writer, scitex-stats, figrecipe, etc.), each with their own documentation, versions, APIs, and CLI commands. Keeping them in sync, discovering what's available, and maintaining consistency across the ecosystem becomes increasingly difficult as it grows.

## Solution

`scitex-dev` provides a unified toolkit for developing and maintaining the SciTeX ecosystem:

- **Docs aggregation** — discover, build, and search documentation across all packages from a single entry point
- **Unified search** — search Python APIs, CLI commands, MCP tools, and docs with fuzzy matching and Google-like syntax
- **Version management** — track, compare, and fix version mismatches across pyproject.toml, `__init__.py`, git tags, PyPI, and RTD
- **Bulk rename** — safe, preview-able renaming with cross-reference updates across the entire codebase
- **LLM-friendly types** — `Result`, `ErrorCode`, `@supports_return_as` for consistent structured responses

Zero runtime dependencies. Pure stdlib.

## Installation

```bash
pip install scitex-dev

# With CLI support:
pip install scitex-dev[cli]

# With MCP server:
pip install scitex-dev[mcp]

# Everything:
pip install scitex-dev[all]
```

## Quick Start

```python
import scitex_dev

# Unified search across the ecosystem
results = scitex_dev.search("save figure")

# Version management
versions = scitex_dev.list_versions()
mismatches = scitex_dev.get_mismatches()

# Documentation aggregation
docs = scitex_dev.get_docs(package="scitex-writer", format="json")
```

## Three Interfaces

<details>
<summary><b>Python API</b></summary>

```python
import scitex_dev

# Search
scitex_dev.search("ttest", scope="api")
scitex_dev.search('+required -excluded "exact phrase"')

# Docs
scitex_dev.get_docs()
scitex_dev.get_docs(package="scitex-writer", format="json")
scitex_dev.build_docs(package="scitex-writer")
scitex_dev.search_docs("installation")

# Versions
scitex_dev.list_versions()
scitex_dev.check_versions(["scitex", "figrecipe"])
scitex_dev.get_mismatches()
scitex_dev.fix_mismatches(dry_run=True)

# LLM-friendly types
from scitex_dev import Result, supports_return_as

@supports_return_as
def my_function(x: int) -> int:
    return x * 2

result = my_function(5, return_as="result")
# Result(success=True, data=10)
```

</details>

<details>
<summary><b>CLI Commands</b></summary>

```bash
# Version management
scitex-dev versions
scitex-dev fix-mismatches --dry-run

# Documentation
scitex-dev docs --package scitex-writer
scitex-dev search "save figure"

# Bulk rename
scitex-dev rename old_name new_name --dry-run

# See all commands
scitex-dev --help
scitex-dev --help-recursive
```

</details>

<details>
<summary><b>MCP Server</b></summary>

```bash
# Start server
scitex-dev mcp start

# Check setup
scitex-dev mcp doctor
scitex-dev mcp list-tools

# Installation info
scitex-dev mcp installation
```

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "scitex-dev": {
      "command": "scitex-dev",
      "args": ["mcp", "start"]
    }
  }
}
```

</details>

## Part of SciTeX

`scitex-dev` is part of [SciTeX](https://scitex.ai). It provides the shared infrastructure that keeps the ecosystem consistent and discoverable. When used with the orchestrator package `scitex`, it enables unified version management and documentation across all modules:

```python
import scitex_dev

# See the entire ecosystem at a glance
versions = scitex_dev.list_versions()
mismatches = scitex_dev.get_mismatches()

# Search across all installed SciTeX packages
scitex_dev.search("statistical test")
```

The SciTeX ecosystem follows the **Four Freedoms** for researchers:

- **Freedom 0** — Run the software for any research purpose
- **Freedom 1** — Study and modify the source code
- **Freedom 2** — Share copies with colleagues
- **Freedom 3** — Share your modifications with the community

## License

AGPL-3.0-only. See [LICENSE](LICENSE).

---

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/scitex-icon-navy-inverted.png" alt="SciTeX" width="40">
  </a>
</p>
