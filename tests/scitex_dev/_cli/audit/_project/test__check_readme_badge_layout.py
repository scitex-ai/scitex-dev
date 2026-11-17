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

import pytest

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


def _rows(first, second):
    return (
        '<!-- scitex-badges:start --><p align="center">'
        + first + '</p><p align="center">' + second
        + '</p><!-- scitex-badges:end -->'
    )


@pytest.mark.parametrize("separator", ["&amp;", "&#38;", "&#x26;"])
@pytest.mark.parametrize("wrong_row", ["first", "second"])
def test_html_escaped_wrong_row_labels_remain_findings(tmp_path, separator, wrong_row):
    # Arrange
    base = "https://img.shields.io/github/actions/workflow/status/o/r/tests.yml?branch=develop"
    first_label = "tests" if wrong_row == "first" else "pypi"
    second_label = "pypi" if wrong_row == "second" else "tests"
    _write_readme(tmp_path, _rows(
        f'<img src="{base}{separator}label={first_label}">',
        f'<img src="{base}{separator}label={second_label}">',
    ))
    findings = []
    # Act
    check_ps167_readme_badge_layout(tmp_path, _StubViolation, findings)
    # Assert
    assert [v.rule for v in findings] == ["PS-167"]


@pytest.mark.parametrize("separator", ["&", "&amp;"])
def test_percent_encoded_canonical_row_labels_are_consistent(tmp_path, separator):
    # Arrange
    base = "https://img.shields.io/github/actions/workflow/status/o/r/tests.yml?branch=develop"
    _write_readme(tmp_path, _rows(
        f'<img src="{base}{separator}label=%70ypi">',
        f'<img src="{base}{separator}label=%74ests">',
    ))
    findings = []
    # Act
    check_ps167_readme_badge_layout(tmp_path, _StubViolation, findings)
    # Assert
    assert findings == []


def test_non_badge_link_cannot_mask_wrong_row_badge(tmp_path):
    # Arrange
    badge = '<img src="https://img.shields.io/pypi/v/demo?label=pypi">'
    decoy = '<a href="https://example.invalid/?label=tests">unrelated link</a>'
    _write_readme(tmp_path, _rows(badge, badge + decoy))
    findings = []
    # Act
    check_ps167_readme_badge_layout(tmp_path, _StubViolation, findings)
    # Assert
    assert [v.rule for v in findings] == ["PS-167"]
