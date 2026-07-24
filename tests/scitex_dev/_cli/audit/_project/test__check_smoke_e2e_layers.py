"""Tests for `_check_smoke_e2e_layers.py` (PS-211 / PS-212).

PS-211 (W) — package is missing a `tests/smoke/` layer (or the `smoke`
             pytest marker registration).
PS-212 (W) — package is missing a `tests/e2e/` layer (or the `e2e`
             pytest marker registration).

Both checkers are exercised directly with a stub Violation class:
one trigger arm (bare repo) + one clean control arm (layer + marker),
plus the documented opt-out arm.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_smoke_e2e_layers import (
    check_ps211_smoke_layer,
    check_ps212_e2e_layer,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write_markers(repo: Path, *names: str) -> None:
    entries = "\n".join(f'    "{n}: {n} tests",' for n in names)
    (repo / "pyproject.toml").write_text(
        "[project]\n"
        'name = "scitex-demo"\n'
        "[tool.pytest.ini_options]\n"
        f"markers = [\n{entries}\n]\n",
        encoding="utf-8",
    )


def _add_layer(repo: Path, layer: str) -> None:
    d = repo / "tests" / layer
    d.mkdir(parents=True, exist_ok=True)
    (d / "test_happy.py").write_text("def test_it():\n    assert True\n")


# ===== PS-211 =====


class TestPS211SmokeLayer:
    def test_missing_smoke_layer_is_flagged(self, tmp_path: Path) -> None:
        # Arrange — bare repo, no tests/smoke/, no opt-out
        out: list = []
        # Act
        check_ps211_smoke_layer(tmp_path, _StubViolation, out)
        # Assert
        assert [v.rule for v in out] == ["PS-211"]

    def test_smoke_layer_and_marker_produce_no_finding(self, tmp_path: Path) -> None:
        # Arrange — control arm: real smoke tests + registered marker
        _add_layer(tmp_path, "smoke")
        _write_markers(tmp_path, "smoke")
        out: list = []
        # Act
        check_ps211_smoke_layer(tmp_path, _StubViolation, out)
        # Assert
        assert out == []

    def test_no_cli_optout_suppresses_finding(self, tmp_path: Path) -> None:
        # Arrange — documented opt-out for CLI-less packages
        (tmp_path / "pyproject.toml").write_text(
            "[tool.scitex_dev]\nno_cli = true\n"
        )
        out: list = []
        # Act
        check_ps211_smoke_layer(tmp_path, _StubViolation, out)
        # Assert
        assert out == []


# ===== PS-212 =====


class TestPS212E2ELayer:
    def test_missing_e2e_layer_is_flagged(self, tmp_path: Path) -> None:
        # Arrange — bare repo, no tests/e2e/, no opt-out
        out: list = []
        # Act
        check_ps212_e2e_layer(tmp_path, _StubViolation, out)
        # Assert
        assert [v.rule for v in out] == ["PS-212"]

    def test_e2e_layer_and_marker_produce_no_finding(self, tmp_path: Path) -> None:
        # Arrange — control arm: real e2e tests + registered marker
        _add_layer(tmp_path, "e2e")
        _write_markers(tmp_path, "e2e")
        out: list = []
        # Act
        check_ps212_e2e_layer(tmp_path, _StubViolation, out)
        # Assert
        assert out == []

    def test_no_e2e_optout_suppresses_finding(self, tmp_path: Path) -> None:
        # Arrange — documented opt-out
        (tmp_path / "pyproject.toml").write_text(
            "[tool.scitex_dev]\nno_e2e = true\n"
        )
        out: list = []
        # Act
        check_ps212_e2e_layer(tmp_path, _StubViolation, out)
        # Assert
        assert out == []
