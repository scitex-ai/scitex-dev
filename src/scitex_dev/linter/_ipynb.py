#!/usr/bin/env python3
"""Jupyter notebook (.ipynb) linting support — extract code cells and lint.

Scholar-linter Phase 1 for issue #7. Phase 2 (notebook-specific rules
like `NB001`: raw-matplotlib in code cell) to follow in a dedicated
checker class.

Uses stdlib `json` — no nbformat dependency. Each code cell is linted
independently by reusing `lint_source`. Its internal filepath label is
suffixed `::cell-N`, which is visible in opt-in parser errors. Returned
Issue values have cell-relative lines but no filepath or cell identity;
per-cell attribution in normal finding output remains unresolved.
"""

from __future__ import annotations

import json
from pathlib import Path

# Rules that don't make sense per-cell in a notebook context.
# Notebooks are interactive; they have no `__main__` guard, no shebang,
# and rarely a top-level docstring per cell.
_NOTEBOOK_SKIP_RULES = {
    "STX-S001",  # Missing shebang
    "STX-S002",  # Missing `if __name__ == '__main__'` guard
    "STX-S003",  # Missing module docstring
    "STX-S004",  # Missing EOF marker
    "STX-S005",  # Missing timestamp
}


def _validate_notebook_input(notebook, path: Path) -> None:
    """Validate only the structure needed to extract Python code cells."""
    if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
        raise ValueError(f"Notebook {path} requires a cells list")
    for index, cell in enumerate(notebook["cells"]):
        if not isinstance(cell, dict) or cell.get("cell_type") not in ("code", "markdown", "raw"):
            raise ValueError(f"Notebook {path}: invalid cell type at cell {index}")
        if cell["cell_type"] != "code":
            continue
        source = cell.get("source")
        if not (isinstance(source, str) or
                (isinstance(source, list) and all(isinstance(line, str) for line in source))):
            raise ValueError(f"Notebook {path}: code cell {index} source must be text or a list of text")


def lint_ipynb(path: Path, config=None, *, raise_input_errors: bool = False) -> list:
    """Lint a Jupyter notebook by extracting code cells and running
    `lint_source` on each. Returns a flat list of Issue objects.

    The checker receives ``"/path/to/notebook.ipynb::cell-N"`` as a parse
    label. Returned Issue values retain cell-relative line numbers but do not
    carry that label; formatters use the separately supplied outer filepath.
    Opt in with ``raise_input_errors`` to expose read/JSON, extractable-cell
    structure and Python AST errors; this is not complete nbformat validation.
    """
    from .checker import lint_source

    try:
        nb = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        if raise_input_errors:
            raise
        return []

    if raise_input_errors:
        _validate_notebook_input(nb, path)

    issues: list = []
    cells = nb.get("cells", []) or []
    for i, cell in enumerate(cells):
        if cell.get("cell_type") != "code":
            continue
        src_val = cell.get("source", "")
        source = "".join(src_val) if isinstance(src_val, list) else src_val
        if not source.strip():
            continue
        fake_path = f"{path}::cell-{i}"
        cell_issues = lint_source(source, filepath=fake_path, config=config, raise_input_errors=raise_input_errors)
        issues.extend(
            iss for iss in cell_issues if iss.rule.id not in _NOTEBOOK_SKIP_RULES
        )
    return issues


# EOF
