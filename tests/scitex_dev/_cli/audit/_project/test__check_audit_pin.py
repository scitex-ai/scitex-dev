"""Tests for `_check_audit_pin.py` (PS-150 / PS-151).

PS-150 (W) — pyproject.toml declares neither `scitex-dev` in
             `[project.dependencies]` nor in
             `[project.optional-dependencies.dev]`, so the audit gate
             (`shutil.which("scitex-dev")`) silently skips in a fresh venv.
PS-151 (W) — `scitex-dev` is declared but the version floor is below the
             known-good minimum (or is unpinned).

The checker is exercised directly (never via the CLI banner), with a
stub Violation class, one trigger arm + one clean control arm per rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_audit_pin import (
    MIN_KNOWN_GOOD,
    check_audit_pin,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write_pyproject(repo: Path, body: str) -> None:
    (repo / "pyproject.toml").write_text(body, encoding="utf-8")


_NO_SCITEX_DEV = """\
[project]
name = "scitex-demo"
version = "0.1.0"
dependencies = ["click>=8.0"]
[project.optional-dependencies]
dev = [
    "ruff",
    "pytest>=8.0",
]
"""

_PINNED_OK = f"""\
[project]
name = "scitex-demo"
version = "0.1.0"
dependencies = ["click>=8.0"]
[project.optional-dependencies]
dev = [
    "ruff",
    "scitex-dev>={MIN_KNOWN_GOOD}",
]
"""

_PIN_TOO_OLD = """\
[project]
name = "scitex-demo"
version = "0.1.0"
dependencies = ["click>=8.0"]
[project.optional-dependencies]
dev = [
    "scitex-dev>=0.0.1",
]
"""

_PIN_UNPINNED = """\
[project]
name = "scitex-demo"
version = "0.1.0"
dependencies = ["click>=8.0"]
[project.optional-dependencies]
dev = [
    "scitex-dev",
]
"""


# ===== PS-150 =====


class TestPS150:
    def test_missing_scitex_dev_pin_is_flagged(self, tmp_path: Path) -> None:
        # Arrange
        _write_pyproject(tmp_path, _NO_SCITEX_DEV)
        out: list = []
        # Act
        check_audit_pin(tmp_path, _StubViolation, out)
        # Assert
        assert [v.rule for v in out] == ["PS-150"]

    def test_pinned_dev_extra_produces_no_ps150(self, tmp_path: Path) -> None:
        # Arrange — control arm: scitex-dev is present at the known-good floor
        _write_pyproject(tmp_path, _PINNED_OK)
        out: list = []
        # Act
        check_audit_pin(tmp_path, _StubViolation, out)
        # Assert
        assert out == []


# ===== PS-151 =====


class TestPS151:
    def test_floor_below_known_good_is_flagged(self, tmp_path: Path) -> None:
        # Arrange
        _write_pyproject(tmp_path, _PIN_TOO_OLD)
        out: list = []
        # Act
        check_audit_pin(tmp_path, _StubViolation, out)
        # Assert
        assert [v.rule for v in out] == ["PS-151"]

    def test_unpinned_scitex_dev_is_flagged_as_ps151(self, tmp_path: Path) -> None:
        # Arrange — declared but no version floor
        _write_pyproject(tmp_path, _PIN_UNPINNED)
        out: list = []
        # Act
        check_audit_pin(tmp_path, _StubViolation, out)
        # Assert
        assert [v.rule for v in out] == ["PS-151"]

    def test_known_good_floor_produces_no_ps151(self, tmp_path: Path) -> None:
        # Arrange — control arm: floor is exactly the known-good version
        _write_pyproject(tmp_path, _PINNED_OK)
        out: list = []
        # Act
        check_audit_pin(tmp_path, _StubViolation, out)
        # Assert
        assert [v.rule for v in out if v.rule == "PS-151"] == []
