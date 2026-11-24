#!/usr/bin/env python3
"""Filetype dispatch for ``lint_file``.

Routes paths to the right extractor:
- ``.ipynb``                -> ``_ipynb.lint_ipynb`` (notebook cells)
- ``.md`` / ``.markdown``   -> ``_md.lint_md`` (fenced ``python`` blocks)
- ``.rst``                  -> ``_rst.lint_rst`` (Python directives)
- everything else           -> ``lint_source`` on the raw text

Lives outside ``checker.py`` so the orchestrator stays under the line
budget and so each filetype handler can grow independently.
"""

from __future__ import annotations

from pathlib import Path


def lint_file(filepath: str, config=None, *, raise_input_errors: bool = False) -> list:
    """Lint a Python file, Jupyter notebook, or markdown file.

    Returns ``Issue`` objects. By default missing files yield ``[]`` and
    handler read/parse behavior remains compatible. ``raise_input_errors=True``
    raises for unavailable targets and propagates supported handler read,
    notebook code-cell structure/JSON and extracted Python AST errors.

    Raises ``LinterPluginError`` when the file's project type requires a
    plugin capability no installed provider declares (e.g. a
    ``project-type: research`` project without scitex-io's ``raw-io``
    coverage): every file-linting entry point (CLI ``validate-files``, the
    edit hook, MCP, sweep) refuses to report "clean" on a reduced rule
    corpus. See ``_research_scope.check_required_capabilities``.
    """
    from ._plugin_loader import load_plugins
    from ._research_scope import check_required_capabilities
    from .checker import lint_source
    from .config import load_config

    path = Path(filepath)
    if not path.exists() or not path.is_file():
        if raise_input_errors:
            if not path.exists():
                raise FileNotFoundError(f"Lint target does not exist: {filepath}")
            raise ValueError(f"Lint target must be a regular file: {filepath}")
        return []
    if config is None:
        config = load_config(start_path=str(path))
    check_required_capabilities(config, load_plugins().get("capabilities", {}))

    suffix = path.suffix.lower()
    if suffix == ".ipynb":
        from ._ipynb import lint_ipynb

        return lint_ipynb(path, config=config, raise_input_errors=raise_input_errors)
    if suffix in (".md", ".markdown"):
        from ._md import lint_md

        return lint_md(path, config=config, raise_input_errors=raise_input_errors)
    if suffix == ".rst":
        from ._rst import lint_rst

        return lint_rst(path, config=config, raise_input_errors=raise_input_errors)

    source = path.read_text(encoding="utf-8")
    return lint_source(source, filepath=str(path), config=config, raise_input_errors=raise_input_errors)


# EOF
