"""Mirror tests for `_checks/_no_mocks.py` — PA-306 mock detection.

The mock-bearing source is written as string literals into `tmp_path`, so the
auditor's AST pass over THIS test file sees only `ast.Constant` strings (not
real imports / fixtures) and stays clean — the same technique `test__audit.py`
uses.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._api._checks._no_mocks import _audit_no_mocks


def _write_init(tmp_path: Path, body: str) -> Path:
    pkg_dir = tmp_path / "fakepkg"
    pkg_dir.mkdir()
    init = pkg_dir / "__init__.py"
    init.write_text(body)
    return init


def test_audit_no_mocks_flags_mock_library_import(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "impl.py").write_text(
        "from unittest.mock import patch\ndef f():\n    return patch\n"
    )
    codes = {v.rule for v in _audit_no_mocks(init, "fakepkg", "fakepkg")}
    assert "PA-306" in codes


def test_audit_no_mocks_flags_mocker_fixture_param(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "test_x.py").write_text(
        "def test_thing(mocker, tmp_path):\n    return tmp_path\n"
    )
    codes = {v.rule for v in _audit_no_mocks(init, "fakepkg", "fakepkg")}
    assert "PA-306" in codes


def test_audit_no_mocks_passes_clean_source(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "impl.py").write_text("def f(tmp_path):\n    return tmp_path\n")
    assert _audit_no_mocks(init, "fakepkg", "fakepkg") == []
