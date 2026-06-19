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
