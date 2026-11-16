"""Filetype dispatch for ``lint_file``.

Routes paths to the right extractor:
- ``.ipynb``                -> ``_ipynb.lint_ipynb`` (notebook cells)
- ``.md`` / ``.markdown``   -> ``_md.lint_md`` (fenced ``python`` blocks)
- everything else           -> ``lint_source`` on the raw text

Lives outside ``checker.py`` so the orchestrator stays under the line
budget and so each filetype handler can grow independently.
"""

from __future__ import annotations

from pathlib import Path


def lint_file(filepath: str, config=None) -> list:
    """Lint a Python file, Jupyter notebook, or markdown file.

    Returns a list of ``Issue`` objects. Missing files yield ``[]``.

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
        return []
    if config is None:
        config = load_config(start_path=str(path))
    check_required_capabilities(config, load_plugins().get("capabilities", {}))

    suffix = path.suffix.lower()
    if suffix == ".ipynb":
        from ._ipynb import lint_ipynb

        return lint_ipynb(path, config=config)
    if suffix in (".md", ".markdown"):
        from ._md import lint_md

        return lint_md(path, config=config)
    if suffix == ".rst":
        from ._rst import lint_rst

        return lint_rst(path, config=config)

    source = path.read_text(encoding="utf-8")
    return lint_source(source, filepath=str(path), config=config)


# EOF
