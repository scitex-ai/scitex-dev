"""Tests for `_check_placeholder_tests` — PS-206b focus.

PS-206b (W) — a test file has a collectable `def test_*` but NO
assertion anywhere in the module (the auto-generated importlib
import-smoke pattern). Adding any real assertion clears it; a
`# PS-206b: import-smoke-allowed` comment opts out.

The checker is exercised directly (it appends real `Violation`
instances to `out`); assertions are scoped to PS-206b.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._project._checks import _check_placeholder_tests


def _write_test_file(repo: Path, body: str) -> None:
    d = repo / "tests" / "scitex_demo"
    d.mkdir(parents=True, exist_ok=True)
    (d / "test_smoke.py").write_text(body, encoding="utf-8")


# A collectable test function with NO assertion — pure import smoke.
_IMPORT_SMOKE = (
    "import importlib\n\n\n"
    "def test_module_imports():\n"
    '    importlib.import_module("scitex_demo._foo")\n'
)

# Same function, but with a real assertion.
_WITH_ASSERTION = (
    "import importlib\n\n\n"
    "def test_module_imports():\n"
    '    mod = importlib.import_module("scitex_demo._foo")\n'
    "    assert mod is not None\n"
)

# Import smoke with the documented opt-out comment.
_OPTED_OUT = (
    "import importlib\n\n"
    "# PS-206b: import-smoke-allowed\n\n\n"
    "def test_module_imports():\n"
    '    importlib.import_module("scitex_demo._foo")\n'
)


def _ps206b(repo: Path) -> list[str]:
    out: list = []
    _check_placeholder_tests(repo, out)
    return [v.rule for v in out if v.rule == "PS-206b"]


class TestPS206bImportSmokeOnly:
    def test_import_smoke_only_test_is_flagged(self, tmp_path: Path) -> None:
        # Arrange
        _write_test_file(tmp_path, _IMPORT_SMOKE)
        # Act
        fired = _ps206b(tmp_path)
        # Assert
        assert fired == ["PS-206b"]

    def test_test_with_assertion_produces_no_ps206b(self, tmp_path: Path) -> None:
        # Arrange — control arm: a real assertion exercises behaviour
        _write_test_file(tmp_path, _WITH_ASSERTION)
        # Act
        fired = _ps206b(tmp_path)
        # Assert
        assert fired == []

    def test_optout_comment_suppresses_ps206b(self, tmp_path: Path) -> None:
        # Arrange — documented opt-out marker present
        _write_test_file(tmp_path, _OPTED_OUT)
        # Act
        fired = _ps206b(tmp_path)
        # Assert
        assert fired == []
