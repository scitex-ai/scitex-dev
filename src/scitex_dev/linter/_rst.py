#!/usr/bin/env python3
"""reStructuredText (`*.rst`) linting — extract Python code-block
directives and lint each one.

Mirrors the shape of ``_md.py`` / ``_ipynb.py``. Recognised directives:

- ``.. code-block:: python`` (Sphinx)
- ``.. code:: python``       (docutils)
- ``.. sourcecode:: python`` (docutils)
- ``.. ipython:: python``    (Sphinx ipython)

Directive options (``:linenos:``, ``:emphasize-lines:``, …) are
skipped, then the contiguous indented block is captured, dedented, and
linted.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from ._md import _SNIPPET_SKIP_RULES

_DIRECTIVE_RE = re.compile(
    r"^(?P<indent>[ \t]*)\.\. (?:code-block|code|sourcecode|ipython)::"
    r"[ \t]*(?:python|py)(?=[ \t\r\n])[^\n]*\n",
    re.IGNORECASE,
)


def _iter_python_blocks(text: str):
    """Yield ``(block_index, start_line, body)`` for each python directive.

    ``start_line`` is 1-indexed and points at the first body line so
    issue line numbers map back to source. Option scanning stops at a
    nonblank line dedented to the directive level or beyond, or at the first
    blank separator. Later colon-prefixed lines belong to code content.
    """
    lines = text.splitlines(keepends=True)
    block_idx = 0
    i = 0
    while i < len(lines):
        m = _DIRECTIVE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        directive_indent = len(m.group("indent"))
        i += 1
        # Options precede the blank separator. Colon-prefixed lines after
        # that separator are code content, not additional directive options.
        while i < len(lines):
            stripped = lines[i].strip()
            line_indent = len(lines[i]) - len(lines[i].lstrip(" \t"))
            if not stripped.startswith(":") or line_indent <= directive_indent:
                break
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        # Capture body: contiguous lines indented strictly more than
        # the directive itself (blank lines preserved within the block).
        body_start = i
        body_lines: list = []
        while i < len(lines):
            line = lines[i]
            if line.strip() == "":
                body_lines.append(line)
                i += 1
                continue
            line_indent = len(line) - len(line.lstrip(" \t"))
            if line_indent <= directive_indent:
                break
            body_lines.append(line)
            i += 1
        # Trim trailing blank lines from the captured body.
        while body_lines and body_lines[-1].strip() == "":
            body_lines.pop()
        if not body_lines:
            continue
        body = textwrap.dedent("".join(body_lines))
        yield block_idx, body_start + 1, body
        block_idx += 1


def lint_rst(path: Path, config=None, *, raise_input_errors: bool = False) -> list:
    """Lint Python ``code-block`` directives inside an RST file.

    The checker receives ``"/path/to/index.rst::block-N"`` as a parse
    label, visible in opt-in syntax errors with block-relative locations.
    Returned Issue lines are shifted into the document; the block label is
    not retained in Issue values or normal formatter output.
    ``raise_input_errors`` exposes read and extracted Python AST errors;
    recognized directives are extraction, not complete document validation.
    """
    from .checker import lint_source

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        if raise_input_errors:
            raise
        return []

    issues: list = []
    for idx, start_line, body in _iter_python_blocks(text):
        if not body.strip():
            continue
        fake_path = f"{path}::block-{idx}"
        block_issues = lint_source(body, filepath=fake_path, config=config, raise_input_errors=raise_input_errors)
        for iss in block_issues:
            if iss.rule.id in _SNIPPET_SKIP_RULES:
                continue
            iss.line = start_line + (iss.line - 1)
            issues.append(iss)
    return issues


# EOF
