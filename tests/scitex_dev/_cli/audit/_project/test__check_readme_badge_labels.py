"""Tests for `_check_readme_badge_labels.py` (PS-166).

PS-166 (W) — a shields.io badge in README.md uses a non-standard
`?label=...` value (or omits the label on a route whose auto-generated
label is non-standard). Allowed short labels: pypi, python, docs, tests,
install-check, quality, cov.

The checker is exercised directly with a stub Violation class.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_readme_badge_labels import (
    check_ps166_readme_badge_labels,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write_readme(repo: Path, body: str) -> None:
    (repo / "README.md").write_text(body, encoding="utf-8")


# A shields workflow-status badge with a non-standard capitalized label.
_NONSTANDARD_LABEL = (
    "# demo\n\n"
    "![tests](https://img.shields.io/github/actions/workflow/status/"
    "owner/demo/pytest.yml?label=Tests)\n"
)

# Same badge, but with the standardized short label.
_STANDARD_LABEL = (
    "# demo\n\n"
    "![tests](https://img.shields.io/github/actions/workflow/status/"
    "owner/demo/pytest.yml?label=tests)\n"
)


class TestPS166BadgeLabels:
    def test_nonstandard_label_is_flagged(self, tmp_path: Path) -> None:
        # Arrange
        _write_readme(tmp_path, _NONSTANDARD_LABEL)
        out: list = []
        # Act
        check_ps166_readme_badge_labels(tmp_path, _StubViolation, out)
        # Assert
        assert [v.rule for v in out] == ["PS-166"]

    def test_standard_label_produces_no_finding(self, tmp_path: Path) -> None:
        # Arrange — control arm: canonical short label
        _write_readme(tmp_path, _STANDARD_LABEL)
        out: list = []
        # Act
        check_ps166_readme_badge_labels(tmp_path, _StubViolation, out)
        # Assert
        assert out == []
