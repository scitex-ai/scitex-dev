"""README body-content rules — PS-144 (P&S table cells), PS-154 (Installation).

One rule-family per module (see `_readme_structure_shared` for the split
rationale).

PS-144: `## Problem and Solution` table cells must (a) contain at
least one `**bold**` span, (b) keep bold coverage <= 30% of cell
text, and (c) stay <= 200 characters per cell (one sentence per cell).

PS-154: `## Installation` section must start with one
`uv pip install "<pkg>[all]"` fenced bash line; any per-module
extras matrix table must live inside a `<details>` block.
"""

from __future__ import annotations

import re

from ._readme_structure_shared import (
    RE_PIPE_TABLE,
    strip_details_spans,
)


# --- PS-144: Problem and Solution table cell quality -----------------------

_RE_BOLD_SPAN = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BOLD_MAX_RATIO = 0.30
_CELL_MAX_CHARS = 200

# PS-154 — Installation: detect `uv pip install ...` fenced bash blocks.
_RE_UV_PIP_INSTALL = re.compile(
    r"```(?:bash|sh|shell|console)?\s*\n[^\n`]*?uv\s+pip\s+install\b",
    re.IGNORECASE,
)


def table_rows(body: str) -> list[list[str]]:
    """Extract data rows (skipping header + separator) from the first
    pipe-table found in `body`. Returns a list[list[str]] of cells."""
    rows: list[list[str]] = []
    in_table = False
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if in_table:
                break
            continue
        in_table = True
        # Skip separator (`|---|---|`).
        if re.fullmatch(r"\|[\s\-:|]+\|", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        rows.append(cells)
    return rows[1:] if rows else []  # drop header row


def cell_bold_problems(cell: str) -> list[str]:
    """Return list of PS-144 sub-issues for a single cell."""
    out: list[str] = []
    if len(cell) > _CELL_MAX_CHARS:
        out.append(f"cell length {len(cell)} > {_CELL_MAX_CHARS} chars")
    bolds = _RE_BOLD_SPAN.findall(cell)
    if not bolds:
        out.append("no `**bold**` span")
        return out
    bold_chars = sum(len(b) for b in bolds)
    plain_chars = max(len(cell), 1)
    ratio = bold_chars / plain_chars
    if ratio > _BOLD_MAX_RATIO:
        out.append(f"bold covers {ratio * 100:.0f}% > {int(_BOLD_MAX_RATIO * 100)}%")
    return out


def check_problem_solution_table(
    readme_path: str,
    violation_cls: type,
    out: list,
    *,
    pas: tuple[str, int, int] | None,
) -> None:
    """PS-144: `## Problem and Solution` table cell rules."""
    if pas is None:
        return
    body, _s, _e = pas
    rows = table_rows(body)
    for row_idx, cells in enumerate(rows, start=1):
        # Convention: `| # | Problem | Solution |` — index col + 2 data cols.
        if len(cells) < 3:
            continue
        for col_label, cell in (("Problem", cells[1]), ("Solution", cells[2])):
            for issue in cell_bold_problems(cell):
                out.append(
                    violation_cls(
                        "PS-144",
                        readme_path,
                        f"row {row_idx} {col_label}: {issue}",
                    )
                )


def check_installation(
    readme_path: str,
    violation_cls: type,
    out: list,
    *,
    install: tuple[str, int, int] | None,
) -> None:
    """PS-154: Installation section structure."""
    if install is None:
        return
    body, _s, _e = install
    if not _RE_UV_PIP_INSTALL.search(body):
        out.append(
            violation_cls(
                "PS-154",
                readme_path,
                (
                    "Installation section should start with one "
                    '`uv pip install "<pkg>[all]"` line; per-module '
                    "extras matrix must live inside a `<details>` "
                    "block. See scitex-io README §Installation"
                ),
            )
        )
        return
    # Any pipe-table outside of <details>...</details>? Blank the
    # <details> regions, then look for pipe-tables in the remainder.
    if RE_PIPE_TABLE.search(strip_details_spans(body)):
        out.append(
            violation_cls(
                "PS-154",
                readme_path,
                (
                    "Installation section has an extras matrix "
                    "table outside a `<details>` block — wrap "
                    "the matrix in `<details><summary>…</summary>"
                    "…</details>`. See scitex-io README "
                    "§Installation"
                ),
            )
        )
