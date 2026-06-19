"""Mirror tests for `_checks/_init_surface.py` — `__init__.py` surface audit.

`_audit_init` walks a real on-disk `__init__.py`; `_inspect_version_pattern`
classifies a single `ast.Assign`. Both are exercised with real source written
to `tmp_path` / parsed via `ast`.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

from scitex_dev._cli.audit._api._checks._init_surface import (
    _audit_init,
    _inspect_version_pattern,
)


def _write_init(tmp_path: Path, body: str) -> Path:
    pkg_dir = tmp_path / "fakepkg"
    pkg_dir.mkdir()
    init = pkg_dir / "__init__.py"
    init.write_text(body)
    return init


def test_audit_init_flags_missing_all(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _write_init(tmp_path, "from __future__ import annotations\n")
    codes = {v.rule for v in _audit_init(init, "fakepkg")}
    assert "PA-101" in codes


def test_audit_init_passes_a_canonical_init(tmp_path):
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "from importlib.metadata import PackageNotFoundError, version\n"
        "try:\n"
        "    __version__ = version('fakepkg')\n"
        "except PackageNotFoundError:\n"
        "    __version__ = '0.0.0+local'\n"
        "__all__ = ['__version__']\n"
    )
    init = _write_init(tmp_path, body)
    assert _audit_init(init, "fakepkg") == []


def test_inspect_version_pattern_recognises_metadata_call():
    # Arrange
    # Act
    # Assert
    node = cast(ast.Assign, ast.parse("__version__ = version('x')").body[0])
    assert _inspect_version_pattern(node)[0] is True


def test_inspect_version_pattern_reports_bare_literal_fallback():
    # Arrange
    # Act
    # Assert
    node = cast(ast.Assign, ast.parse("__version__ = '1.2.3'").body[0])
    assert _inspect_version_pattern(node) == (False, "1.2.3")
