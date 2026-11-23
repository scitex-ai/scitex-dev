---
description: |
  [TOPIC] Linter Python API
  [DETAILS] Use the actual top-level list_rules catalog and checker-module
  lint_file/lint_source functions. Keep installed rule coverage and imports separate.
tags: [scitex-dev-linter-python-api]
---

# Python API

`scitex_dev.linter` exports `__version__` and `list_rules(category=None)`.
The catalog combines the installed engine and provider rules. Category matching
uses the actual category strings, such as `io`; it is not an STX ID-prefix filter.

```python
from scitex_dev.linter import list_rules

rules = list_rules(category="io")
```

The checker module exposes the functions used by the CLI and MCP wrappers:

```python
from scitex_dev.linter.checker import lint_source

issues = lint_source("VALUE = 1\n", filepath="tool.py")
```

`lint_file(filepath, config=None)` in that same module reads an existing file;
`lint_source(source, filepath="<stdin>", config=None)` checks a supplied string.
Results contain `Issue` objects with rule metadata and source positions. A
filename can affect config resolution, research/library classification and
coverage, so use the intended path. Checking a string does not execute it.
These are checker-module interfaces, not nonexistent top-level `check`,
`check_source` or `check_files` methods. Source: `linter/__init__.py` and
`linter/checker.py`; owning controls include `tests/scitex_dev/linter/test__emit.py`
and `tests/scitex_dev/linter/test__source_helpers.py`.

Rules and required capabilities remain owned by their providers. Missing
mandatory providers fail; optional unmet requirements can leave reported skips.
A returned catalog or an empty issue list is not complete-environment acceptance.
Configuration readers and the unresolved CLI severity-field gap are documented
in [04_cli-reference.md](04_cli-reference.md).

The distribution declares an STX flake8 extension at
`scitex_dev.linter.flake8_plugin:SciTeXFlake8Checker`; using it also requires a
flake8 installation. See [11_mcp-tools.md](11_mcp-tools.md) for MCP wrappers.
