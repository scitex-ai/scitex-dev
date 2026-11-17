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

import pytest

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


@pytest.mark.parametrize(
    "separator,label,quote",
    [
        ("&amp;", "tests", '"'),
        ("&#38;", "tests", '"'),
        ("&#x26;", "tests", '"'),
        ("&AMP;", "tests", "'"),
        ("&amp;", "te&#115;ts", '"'),
        ("&amp;", "install&#45;check", '"'),
        ("&amp;", "%74ests", '"'),
        ("&", "tests", '"'),
    ],
)
def test_html_character_references_preserve_standard_labels(tmp_path, separator, label, quote):
    # Arrange
    url = "https://img.shields.io/github/actions/workflow/status/o/r/tests.yml?branch=develop"
    _write_readme(tmp_path, f"<img src={quote}{url}{separator}label={label}{quote}>")
    findings = []
    # Act
    check_ps166_readme_badge_labels(tmp_path, _StubViolation, findings)
    # Assert
    assert findings == []


@pytest.mark.parametrize(
    "suffix,nonstandard",
    [
        ("&amp;label=Tests", True),
        ("&amp;label=build", True),
        ("&amp;label=", False),
        ("%26label%3Dtests", False),
        ("&amp;amp;label=tests", False),
        ("", False),
        ("&amp;label=%2574ests", True),
    ],
)
def test_missing_and_nonstandard_labels_still_fail_after_one_decode(tmp_path, suffix, nonstandard):
    # Arrange
    url = "https://img.shields.io/github/actions/workflow/status/o/r/tests.yml?branch=develop"
    _write_readme(tmp_path, f'<img src="{url}{suffix}">')
    findings = []
    # Act
    check_ps166_readme_badge_labels(tmp_path, _StubViolation, findings)
    # Assert
    assert [(v.rule, "non-standard label" in v.detail) for v in findings] == [
        ("PS-166", nonstandard)
    ]


def test_equivalent_plain_and_html_urls_share_one_diagnostic(tmp_path):
    # Arrange
    url = "https://img.shields.io/github/actions/workflow/status/o/r/tests.yml?branch=develop"
    _write_readme(tmp_path, f'<img src="{url}&label=Tests"><img src="{url}&amp;label=Tests">')
    findings = []
    # Act
    check_ps166_readme_badge_labels(tmp_path, _StubViolation, findings)
    # Assert
    assert [(v.rule, "non-standard label" in v.detail) for v in findings] == [("PS-166", True)]


@pytest.mark.parametrize(
    "suffix,standard",
    [
        ("?branch=develop&amp;label=tests&#41;extra", False),
        ("?branch=develop&amp;label=tests&quot;extra", False),
        ("?branch=develop#?label=tests", False),
        ("?branch=develop?label=tests", False),
        ("?branch=develop&amp;label=tests#details", True),
        ("?%6cabel=tests", True),
    ],
)
def test_only_real_query_fields_define_the_label(tmp_path, suffix, standard):
    # Arrange
    base = "https://img.shields.io/github/actions/workflow/status/o/r/tests.yml"
    _write_readme(tmp_path, f'<img src="{base}{suffix}">')
    findings = []
    # Act
    check_ps166_readme_badge_labels(tmp_path, _StubViolation, findings)
    # Assert
    assert [v.rule for v in findings] == ([] if standard else ["PS-166"])
