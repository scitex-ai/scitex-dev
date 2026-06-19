"""Mirror tests for `_checks/_umbrella.py` — PA-304 umbrella-import audit.

A module-level `from scitex.<sub> import ...` inside standalone source trips
PA-304; the umbrella package itself is exempt, and function-scoped (lazy)
umbrella imports are allowed. Real source written to `tmp_path`.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._api._checks._umbrella import _audit_umbrella_imports


def _write_init(tmp_path: Path, body: str) -> Path:
    pkg_dir = tmp_path / "fakepkg"
    pkg_dir.mkdir()
    init = pkg_dir / "__init__.py"
    init.write_text(body)
    return init


def test_audit_umbrella_flags_module_level_umbrella_import(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "impl.py").write_text(
        "from scitex.io import load\ndef f():\n    return load\n"
    )
    codes = {v.rule for v in _audit_umbrella_imports(init, "fakepkg", "fakepkg")}
    assert "PA-304" in codes


def test_audit_umbrella_exempts_the_umbrella_package_itself(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "impl.py").write_text("from scitex.io import load\n")
    assert _audit_umbrella_imports(init, "scitex", "scitex") == []


def test_audit_umbrella_silent_for_function_scoped_import(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "impl.py").write_text(
        "def f():\n    from scitex.io import load\n    return load\n"
    )
    codes = {v.rule for v in _audit_umbrella_imports(init, "fakepkg", "fakepkg")}
    assert "PA-304" not in codes
