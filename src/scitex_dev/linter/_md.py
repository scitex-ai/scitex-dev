#!/usr/bin/env python3
"""Markdown (`*.md`) linting — extract fenced ``python`` code blocks
and lint each one.

Mirrors the shape of ``_ipynb.py``. Each fenced block is linted as if
it were its own file, with an internal ``::block-N`` parser label.
Returned Issue values have document line numbers but no filepath or
block identity; formatters use the separately supplied outer filepath.

Structural rules (missing main guard, missing module docstring, etc.)
do not apply to README snippets, so the same skip set used for
notebook cells is applied here.
"""

from __future__ import annotations

import re
from pathlib import Path

# Same skip set as `_ipynb.py`. Notebook cells and README snippets are
# *interactive examples*, not scripts, so structural rules are noise.
_SNIPPET_SKIP_RULES = {
    "STX-S001",  # Missing @stx.session/@stx.module on main()
    "STX-S002",  # Missing `if __name__ == '__main__'` guard
    "STX-S003",  # Missing module docstring
    "STX-S004",  # Missing EOF marker
    "STX-S005",  # Missing timestamp
}

# Track every fence, including non-Python ones, so apparent Python openers
# inside another fenced block remain literal content.
_FENCE_START_RE = re.compile(r"([ \t]{0,3})(`{3,}|~{3,})[ \t]*([^\r\n]*)")
_FENCE_END_RE = re.compile(r"[ \t]{0,3}(`{3,}|~{3,})[ \t]*")


def _fenced_body(lines: list[str], indentation: str) -> str:
    """Remove only an opening fence's space indentation from its content."""
    body = "".join(lines)
    if "\t" not in indentation:
        body = re.sub(rf"^ {{0,{len(indentation)}}}", "", body, flags=re.MULTILINE)
    return body


def _iter_python_blocks(text: str):
    """Yield Python/py fence index, first document body line and code.

    Backtick and tilde runs use matching characters and a closing run at least
    as long as the opener. An unclosed Python fence continues through EOF.
    This scanner does not parse list or blockquote container structure.
    """
    fence = None
    python = False
    indentation = ""
    body: list[str] = []
    start_line = 0
    block_index = 0
    for line_no, raw_line in enumerate(text.splitlines(keepends=True), 1):
        line = raw_line.rstrip("\r\n")
        if fence is None:
            opening = _FENCE_START_RE.fullmatch(line)
            if not opening:
                continue
            indentation, marker, info = opening.groups()
            if marker[0] == "`" and "`" in info:
                continue
            fence = marker
            language = re.split(r"[ \t]", info.strip(" \t"), maxsplit=1)[0]
            python = language.lower() in {"python", "py"}
            start_line = line_no + 1
            body = []
        elif (closing := _FENCE_END_RE.fullmatch(line)) and (
            closing[1][0] == fence[0] and len(closing[1]) >= len(fence)
        ):
            if python:
                yield block_index, start_line, _fenced_body(body, indentation)
                block_index += 1
            fence = None
        elif python:
            body.append(raw_line)
    if fence is not None and python:
        yield block_index, start_line, _fenced_body(body, indentation)


def lint_md(path: Path, config=None, *, raise_input_errors: bool = False) -> list:
    """Lint a markdown file's fenced ``python`` blocks.

    The checker receives ``"/path/to/README.md::block-N"`` as a parse
    label, visible in opt-in syntax errors with block-relative locations.
    Returned Issue lines are shifted into the document; the block label is
    not retained in Issue values or normal formatter output.
    ``raise_input_errors`` exposes read and extracted AST errors for supported
    fences, including a Python fence that continues to EOF. This is not full
    Markdown validation or analysis of non-Python fenced content.
    """
    from .checker import lint_source

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        if raise_input_errors:
            raise
        return []

    issues: list = []
    for idx, fence_line, body in _iter_python_blocks(text):
        if not body.strip():
            continue
        fake_path = f"{path}::block-{idx}"
        block_issues = lint_source(body, filepath=fake_path, config=config, raise_input_errors=raise_input_errors)
        # Filter snippet-irrelevant rules and shift line numbers so the
        # report points back at the markdown file's actual line.
        for iss in block_issues:
            if iss.rule.id in _SNIPPET_SKIP_RULES:
                continue
            iss.line = fence_line + (iss.line - 1)
            issues.append(iss)
    return issues


# EOF
