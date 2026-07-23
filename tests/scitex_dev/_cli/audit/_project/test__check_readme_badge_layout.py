"""Tests for `_check_readme_badge_layout.py` (PS-167).

PS-167 (W) — README.md badge block deviates from the canonical SAC
two-row layout (missing markers, single row, non-shields image host, or
mis-covered rows).

The checker is exercised directly with a stub Violation class: a trigger
arm (no `scitex-badges:start` marker) and a clean control arm (a full
canonical two-row block that satisfies every sub-check).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_readme_badge_layout import (
    check_ps167_readme_badge_layout,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write_readme(repo: Path, body: str) -> None:
    (repo / "README.md").write_text(body, encoding="utf-8")


# README with badges but no canonical markers at all — trips PS-167.
_NO_MARKERS = (
    "# demo\n\n"
    '<p align="center">\n'
    '  <img src="https://img.shields.io/pypi/v/demo?label=pypi">\n'
    "</p>\n"
)

# A canonical two-row block: markers WRAP two <p align="center"> rows,
# every image is shields.io, row 1 carries a metadata label (pypi) and
# row 2 carries a CI label (tests).
_CANONICAL = (
    "# demo\n\n"
    "<!-- scitex-badges:start -->\n"
    '<p align="center">\n'
    '  <img src="https://img.shields.io/pypi/v/demo?label=pypi">\n'
    '  <img src="https://img.shields.io/pypi/pyversions/demo?label=python">\n'
    "</p>\n"
    '<p align="center">\n'
    '  <img src="https://img.shields.io/github/actions/workflow/status/'
    'owner/demo/pytest.yml?label=tests">\n'
    '  <img src="https://img.shields.io/codecov/c/github/owner/demo?label=cov">\n'
    "</p>\n"
    "<!-- scitex-badges:end -->\n"
)


class TestPS167BadgeLayout:
    def test_missing_start_marker_is_flagged(self, tmp_path: Path) -> None:
        # Arrange
        _write_readme(tmp_path, _NO_MARKERS)
        out: list = []
        # Act
        check_ps167_readme_badge_layout(tmp_path, _StubViolation, out)
        # Assert
        assert [v.rule for v in out] == ["PS-167"]

    def test_canonical_two_row_block_produces_no_finding(
        self, tmp_path: Path
    ) -> None:
        # Arrange — control arm: full canonical layout
        _write_readme(tmp_path, _CANONICAL)
        out: list = []
        # Act
        check_ps167_readme_badge_layout(tmp_path, _StubViolation, out)
        # Assert
        assert out == []
