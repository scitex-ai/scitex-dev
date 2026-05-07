"""File discovery for the linter CLI.

Collects ``*.py`` and ``*.ipynb`` files from a path, honoring the
config's ``exclude_dirs``. Notebook routing happens downstream in
``checker.lint_file``.
"""

from __future__ import annotations

from pathlib import Path

_DEFAULT_SKIP = {
    "__pycache__",
    ".git",
    "node_modules",
    ".tox",
    "venv",
    ".venv",
    ".ipynb_checkpoints",
}


def collect_files(path: Path, recursive: bool = True, config=None) -> list:
    """Return Python + notebook files under ``path``.

    Single files are returned as-is regardless of suffix.
    """
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []

    patterns = ("**/*.py", "**/*.ipynb") if recursive else ("*.py", "*.ipynb")
    skip = set(config.exclude_dirs) if config else set(_DEFAULT_SKIP)

    files: list = []
    for pattern in patterns:
        files.extend(
            p for p in path.glob(pattern) if not any(s in p.parts for s in skip)
        )
    return sorted(set(files))


# EOF
