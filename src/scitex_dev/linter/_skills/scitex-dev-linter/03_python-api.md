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

issues = lint_source("VALUE = 1\n", filepath="tool.py", raise_input_errors=True)
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
By default, `lint_file` still returns no findings for missing/non-file inputs,
and the shared handlers retain their earlier read/parse behavior. `lint_source`
still returns no findings for AST syntax errors unless explicitly requested.
A default file handler can retain earlier findings while a later code unit is
unparseable; the opt-in mode raises instead of returning partial findings.
Use keyword-only `raise_input_errors=True` on either function to expose these
errors instead. File dispatch passes this mode to the notebook, Markdown and
reST handlers; they also accept that keyword. It covers file availability,
handler read errors, notebook JSON/extractable cell structure and Python AST
syntax errors in supported code units. It is not complete notebook/document
validation, compilation or runtime validation.

Both MCP validation endpoints opt in. The source endpoint delegates to the
owning checker rather than parsing the input twice. Existing default Python
and CLI calls retain their behavior; valid supported input yields the same
findings. Sources: `linter/_dispatch.py`, `linter/checker.py`, `_ipynb.py`,
`_md.py` and `_rst.py`; owning compatibility/error controls are in
`tests/scitex_dev/linter/test__dispatch.py`.
Configuration readers and the unresolved CLI severity-field gap are documented
in [04_cli-reference.md](04_cli-reference.md).

`scitex_dev.linter.flake8_plugin:SciTeXFlake8Checker` is an adapter class in
source, but the current Dev distribution declares no `flake8.extension` entry
point. Its automatic plugin integration remains an unresolved gap; class
availability alone is not installed flake8 acceptance. See
[11_mcp-tools.md](11_mcp-tools.md) for MCP wrappers.
