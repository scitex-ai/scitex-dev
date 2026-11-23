---
description: |
  [TOPIC] Linter MCP tools
  [DETAILS] Actual file/source validation and installed rule-catalog contracts;
  distinguish registration from configured server and client availability.
tags: [scitex-dev-linter-mcp-tools]
---

# MCP tools

`linter/_mcp/tools/lint.py::register_lint_tools` registers these tools on a
supplied MCP instance:

| Tool | Contract |
|---|---|
| `linter_check(path, severity="info", category=None)` | Lint one existing regular file and filter reported issues by minimum severity and optional comma-separated categories |
| `linter_check_source(source, filepath="<stdin>")` | Reject Python AST syntax errors, then lint the supplied string without executing it; the filename affects configuration and classification |
| `linter_list_rules(category=None, severity=None)` | Return installed catalog entries and `count`, with optional exact category/severity filters |

The file tool rejects missing and non-regular targets before calling
`checker.lint_file`; directories are not recursively traversed. Existing
regular-file symlinks retain the dispatch behavior of the owning checker.
Python, notebook, Markdown Python fences and reST code blocks use their
respective handlers; other file extensions are analyzed as Python text.
The CLI `validate-files` command has its separate collection path.
Catalog category names are strings such as `io`, not uppercase rule prefixes.
The catalog size depends on installed providers; do not assume a fixed count.

The two validation tools use `formatter.to_json`: `file`, `issues` and `summary`.
Each issue includes `rule_id`, severity, category, line, column (`col`), message,
suggestion and source line. Summary keys are `errors`, `warnings` and `infos`.
These payloads do not prove all optional rule categories ran. The source-string
endpoint rejects syntax errors raised by Python's AST parser before checks
run, with the supplied filename and parser location in the error. AST parser
acceptance does not establish successful compilation or runtime validity; code
is never compiled or executed by this endpoint. The file endpoint opts into
`raise_input_errors=True` on the owning dispatcher. Missing targets, supported
handler read/JSON errors, invalid extractable notebook-cell structure and AST
syntax errors in extracted Python units become tool errors. Existing Python
and CLI callers keep their default behavior unless they opt in.

This checks the handlers' supported extraction: notebook code cells, closed
Markdown Python fences and recognized reST Python directives. Notebook magics
or other non-Python cell syntax can fail AST parsing. Other languages and
non-code cells are not analyzed, and this is not full nbformat, CommonMark or
reST validation. No extracted Python units can still yield an empty result;
that does not prove a full document or corpus was checked.
Mandatory provider failures remain failures, and an in-process registered tool is not evidence that
an external MCP server or consuming client is enabled.

Owning controls: `tests/scitex_dev/linter/_mcp/tools/test_lint.py` and
`tests/scitex_dev/linter/test__emit.py`. Configure and verify the intended server
and client separately before relying on these tool names.

## Skill tools on the full server

The full server calls `_mcp/tools/__init__.py::register_all_tools`, adding
`linter_skills_list()` and `linter_skills_get(name=None)` to the three lint tools.
They use the installed `scitex-dev-linter` namespace owned by `scitex-dev`,
through the same owning skill reader as Dev's CLI. The list result has `success`
and `skills`; get returns `success`, `name` and `content` when available, or a
not-found result. Omitting `name` selects the index. Owner-level selection and
knob opt-outs apply to content; these are separate from server-tool registration.
Reader and resource-validation errors stay visible through MCP instead of being
misreported as a missing Dev installation. Actual in-memory skill-call controls
live alongside the registration tests in
`tests/scitex_dev/linter/_mcp/tools/test_lint.py`.

The server's instructions describe both lint and skill tools. The CLI
`linter mcp list-tools` inspects that actual registry; on import or inspection
failure it exits 1 and reports an error instead of returning guessed tool names.
This remains a registration check, not an execution or external-client check.
CLI catalog and real invalid-setting controls live in
`tests/scitex_dev/linter/test__cmd_mcp.py`.

For supported closed backtick `python`/`py` fences whose opening line has up to
three leading spaces, `_md._iter_python_blocks` removes up to that many spaces
from each code line before parsing, following the [CommonMark indentation
rule](https://spec.commonmark.org/0.31.2/#fenced-code-blocks). Additional Python
indentation is preserved; reported issue lines still point into the document.
Owning extraction and real-finding controls live in
`tests/scitex_dev/linter/test__md.py`. This does not extend fence recognition or
establish full CommonMark validation; tab-prefixed fences retain their earlier
behavior.
