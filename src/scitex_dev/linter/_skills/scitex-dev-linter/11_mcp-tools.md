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
Both severity arguments advertise and accept exactly `error`, `warning` and
`info`, with case-sensitive spelling and no whitespace trimming. Registered
MCP calls reject other strings during argument validation instead of silently
using an unfiltered file threshold or an empty catalog. File validation defaults
to `info`; the catalog's omitted or null severity retains its unfiltered behavior.
These linter choices are separate from the ecosystem audit commands, whose
existing `SeverityChoice` accepts both `warn` and `warning`. The
[owning audit guide](../../../_skills/scitex-dev/39_interface-audit.md) lists the
seven commands and explains the separate unresolved wrapper reporting-floor gap.
Alias parsing does not change audit findings, defaults or exit policies.
Category filters retain their existing exact-string behavior. Owning real-client controls are the `severity_contract`
cases in `tests/scitex_dev/linter/_mcp/tools/test_lint.py`.


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

This checks the handlers' supported extraction: notebook code cells,
Markdown Python fences (including code continuing through EOF) and recognized reST Python directives. Notebook magics
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
