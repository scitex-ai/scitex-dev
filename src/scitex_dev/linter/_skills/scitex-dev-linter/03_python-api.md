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

## Markdown fence extraction

`_md._iter_python_blocks` tracks backtick and tilde fence runs of at least
three characters. A closer uses the same character, at least the opening
length, and only trailing spaces or tabs. A Python fence without a closer
continues through EOF. These boundaries follow the [CommonMark fenced-block
rules](https://spec.commonmark.org/0.31.2/#fenced-code-blocks).

Only complete case-insensitive `python`/`py` language tags select Python.
Other fenced blocks are tracked but their contents are not analyzed, so a
Python-looking opener inside one stays literal text. Backtick info strings
containing a backtick are not accepted as openers. Whitespace-separated metadata
remains accepted after a supported language tag.

For an opening indented up to three spaces, the scanner removes up to that
many spaces per content line while preserving additional Python indentation.
Finding lines map into the document. Existing tab-prefixed behavior remains,
but tab columns, list/blockquote containers and full Markdown validation are
not established. No Python content is compiled or executed. Owning extraction,
syntax-error and real-finding controls are in
`tests/scitex_dev/linter/test__md.py`.

## Finding locations and parser labels

`checker.Issue` stores `rule`, `line`, `col` and `source_line`; it has no
filepath, notebook-cell index or document-block index. `formatter.to_json`
labels the result with the outer `file` argument and does not add unit identity
to issue rows. Plain text formatting likewise uses its supplied outer filepath.

Notebook finding lines are relative to each code cell, so two different cells
can produce findings with the same outer filename and line number. Reliable
per-cell attribution remains an unresolved output-contract gap. Markdown and
reST handlers shift finding lines to physical document lines; columns and source
lines describe the extracted Python after handler indentation removal.

The internal `::cell-N` and `::block-N` labels are passed to Python parsing,
so opt-in syntax errors can identify the code unit. Their parser line/column
location is relative to that extracted unit, not shifted to document lines.
These error labels are separate from the normal finding payload. The owning
source is `_issue.py`, `_ipynb.py`, `_md.py`, `_rst.py` and `formatter.py`. Existing
controls in `tests/scitex_dev/linter/test__dispatch.py`, `test__md.py` and
`_mcp/tools/test_lint.py` cover extraction, document lines and parser error
boundaries; complete per-cell output attribution is not established by them.

For recognized reST Python directives, `_rst._iter_python_blocks` skips an
option-looking colon line only while it is indented beyond the directive
marker and precedes the first blank separator. That separator ends options;
a colon-prefixed code line after it is retained and can trigger a Python AST
error in opt-in mode. A nonblank line at the marker's indentation or less also
ends the option scan, so a following field-list body is not analyzed as
directive Python. This
respects the [directive block indentation boundary](https://docutils.sourceforge.io/docs/ref/rst/restructuredtext.html#directives);
it does not validate directive arguments, option syntax, nested reST or an
empty directive. Owning boundary and real-option/body controls are in
`tests/scitex_dev/linter/test__rst.py`.

Markdown info strings and recognized reST directive arguments select Python
only when the complete first language token is `python` or `py`
(case-insensitive), followed by a space, tab or line ending. Labels such as
`python-console`, `python-repl` and `py-repl` are not Python aliases and their
text is not analyzed by these handlers. Existing whitespace-separated Markdown
metadata after a supported tag remains accepted. Owning tag/extraction and
real-finding controls are in `tests/scitex_dev/linter/test__md.py` and
`test__rst.py`. An empty result for an unsupported language does not establish
that its content or the complete document was validated.

`_cmd_check._do_check` and its compatibility re-export `cli._do_check` also
reject `new_only=True` with the same `click.UsageError` message as the CLI,
before configuration or file analysis. A Python caller cannot enable the
forbidden gate mode through that re-export. Normal validation still reports
pre-existing errors at full severity. Historical `_new_only` classification
utilities remain for compatibility; they are not a supported validation mode.
Owning controls: `tests/scitex_dev/linter/test__cmd_check.py`,
`test__forbid_new_only.py` and `test__new_only.py`.
