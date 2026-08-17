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


def _write_installed_and_source(tmp_path: Path, source_test_body: str) -> tuple:
    """A site-packages-shaped install beside a real checkout.

    Reproduces the 2026-08-16 defect: when the target is importable, the
    auditor's `init_path` points into site-packages, the derived repo root
    collapses to site-packages ITSELF, and `site-packages/tests` — owned by
    an unrelated distribution — gets walked and reported as this package's
    verdict.
    """
    site = tmp_path / "site-packages"
    (site / "fakepkg").mkdir(parents=True)
    installed_init = site / "fakepkg" / "__init__.py"
    installed_init.write_text("from __future__ import annotations\n")
    foreign = site / "tests"
    foreign.mkdir()
    (foreign / "test_other_package.py").write_text(
        "def test_alien(monkeypatch):\n    return monkeypatch\n"
    )
    checkout = tmp_path / "checkout"
    (checkout / "fakepkg").mkdir(parents=True)
    (checkout / "fakepkg" / "__init__.py").write_text("\n")
    (checkout / "tests").mkdir()
    (checkout / "tests" / "test_mine.py").write_text(source_test_body)
    return installed_init, checkout


def test_repo_root_stops_the_scan_reaching_a_foreign_tests_tree(tmp_path):
    # Arrange
    # Act
    # Assert
    installed_init, checkout = _write_installed_and_source(
        tmp_path, "def test_ok(tmp_path):\n    return tmp_path\n"
    )
    assert _audit_no_mocks(
        installed_init, "fakepkg", "fakepkg", repo_root=checkout
    ) == []


def test_repo_root_finds_violations_the_installed_root_cannot_see(tmp_path):
    # Arrange
    # Act
    # Assert
    installed_init, checkout = _write_installed_and_source(
        tmp_path, "def test_mine(monkeypatch):\n    return monkeypatch\n"
    )
    codes = {
        v.rule
        for v in _audit_no_mocks(
            installed_init, "fakepkg", "fakepkg", repo_root=checkout
        )
    }
    assert "PA-306" in codes
