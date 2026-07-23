"""Tests for `_readme_structure_badges.check_badges` — PS-157 focus.

PS-157 (W) — the codecov badge URL inside the canonical badges block is
unbranched (`codecov.io/gh/<owner>/<pkg>/graph/badge.svg`) instead of
pinning a branch (`.../branch/develop/graph/badge.svg`).

`check_badges` also emits PS-155/158/162/163; these tests scope their
assertions to PS-157 so the proof isolates the branch-pinning rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from scitex_dev._cli.audit._project._readme_structure_badges import check_badges


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _block(codecov_url: str) -> str:
    return (
        "<!-- scitex-badges:start -->\n"
        f'<img src="{codecov_url}">\n'
        '<img src="https://img.shields.io/readthedocs/demo">\n'
        "<!-- scitex-badges:end -->\n"
    )


_UNBRANCHED = _block("https://codecov.io/gh/owner/demo/graph/badge.svg")
_BRANCHED = _block("https://codecov.io/gh/owner/demo/branch/develop/graph/badge.svg")


def _ps157(text: str) -> list[str]:
    out: list = []
    check_badges(text, "README.md", _StubViolation, out)
    return [v.rule for v in out if v.rule == "PS-157"]


class TestPS157CodecovBranch:
    def test_unbranched_codecov_badge_is_flagged(self) -> None:
        # Arrange
        text = _UNBRANCHED
        # Act
        fired = _ps157(text)
        # Assert
        assert fired == ["PS-157"]

    def test_branched_codecov_badge_produces_no_ps157(self) -> None:
        # Arrange — control arm: URL pins the develop branch
        text = _BRANCHED
        # Act
        fired = _ps157(text)
        # Assert
        assert fired == []
