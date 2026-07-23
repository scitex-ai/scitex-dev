"""Mirror tests for `_checks/_test_quality.py` — PA-307 test-quality audit.

`_audit_test_quality` re-runs the linter's STX-TQ001-007 across a repo's
`tests/` tree. A real minimal repo (src + tests) is built under `tmp_path`:
an assertion-less test trips PA-307; a well-formed one stays clean.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._api._checks._test_quality import _audit_test_quality


def _make_repo(tmp_path: Path, test_body: str) -> Path:
    """Build <repo>/src/fakepkg/__init__.py + tests/test_sample.py; return init."""
    repo = tmp_path / "fakerepo"
    init = repo / "src" / "fakepkg" / "__init__.py"
    init.parent.mkdir(parents=True)
    init.write_text("from __future__ import annotations\n")
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text(test_body)
    return init


def test_audit_test_quality_flags_assertionless_test(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _make_repo(
        tmp_path,
        "def test_does_a_thing_here():\n    x = 1\n    print(x)\n",
    )
    codes = {v.rule for v in _audit_test_quality(init, "fakepkg", "fakepkg")}
    assert "PA-307" in codes


def test_audit_test_quality_passes_well_formed_test(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _make_repo(
        tmp_path,
        "def test_addition_returns_sum_value():\n"
        "    # Arrange\n"
        "    a = 1\n"
        "    # Act\n"
        "    b = a + 1\n"
        "    # Assert\n"
        "    assert b == 2\n",
    )
    assert _audit_test_quality(init, "fakepkg", "fakepkg") == []


def test_audit_test_quality_prefers_repo_root_over_import_resolved_init(tmp_path):
    # The #435 bug: init_path resolves by import (e.g. an installed wheel in
    # site-packages, which ships NO tests/), while --path/repo_root points at
    # the real checkout carrying a dirty test. TQ must scan repo_root — else it
    # scans the tests-less install, finds nothing, and reports a silent 0.
    # Arrange
    real_init = _make_repo(
        tmp_path, "def test_x_does_something():\n    y = 1\n    print(y)\n"
    )
    real_repo = real_init.parent.parent.parent  # <repo>
    installed_init = tmp_path / "installed" / "fakepkg" / "__init__.py"
    installed_init.parent.mkdir(parents=True)
    installed_init.write_text("from __future__ import annotations\n")
    # Act
    codes = {
        v.rule
        for v in _audit_test_quality(
            installed_init, "fakepkg", "fakepkg", repo_root=real_repo
        )
    }
    # Assert
    assert "PA-307" in codes


def _run_tq_no_tests(tmp_path: Path):
    """Run TQ against an install-like tree that has NO tests/ (the #435 shape)."""
    installed_root = tmp_path / "installed"
    init = installed_root / "fakepkg" / "__init__.py"
    init.parent.mkdir(parents=True)
    init.write_text("from __future__ import annotations\n")
    return _audit_test_quality(init, "fakepkg", "fakepkg", repo_root=installed_root)


def test_audit_test_quality_returns_no_violations_when_no_tests(tmp_path):
    # Arrange
    # Act
    # Assert
    assert _run_tq_no_tests(tmp_path) == []


def test_audit_test_quality_emits_did_not_run_warning_when_no_tests(tmp_path, capsys):
    # A silent 0 reads as a clean pass — the #435 failure mode. Empty
    # candidates must produce a visible skip-warning on stderr.
    # Arrange
    # Act
    _run_tq_no_tests(tmp_path)
    # Assert
    assert "did NOT run" in capsys.readouterr().err


def test_audit_test_quality_no_tests_warning_names_the_stx_tq_gate(tmp_path, capsys):
    # Arrange
    # Act
    _run_tq_no_tests(tmp_path)
    # Assert
    assert "STX-TQ" in capsys.readouterr().err
