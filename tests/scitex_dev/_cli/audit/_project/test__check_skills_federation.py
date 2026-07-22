"""Tests for PS-217 — ``skills`` CLI federation conformance.

Invariant: a leaf that ships a hand-rolled ``src/<pkg>/_cli/_skills.py``
without importing scitex-dev's shared ``skills_click_group`` primitive is
carrying duplicated plumbing and is flagged (WARN) so the
CLI-normalization fan-out stays trackable.

No mocks (NM001-003) — real temp dirs + ``tmp_path``. Single assert per
test (PA-307 §3 STX-TQ007 — one observable per test).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_skills_federation import (
    check_skills_federation,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


# ===== helpers =====


def _make_leaf_skills(tmp_path: Path, body: str, pkg_name: str = "demo_pkg") -> Path:
    """Write ``src/<pkg>/_cli/_skills.py`` with *body*. Returns the repo root."""
    cli_dir = tmp_path / "src" / pkg_name / "_cli"
    cli_dir.mkdir(parents=True)
    (cli_dir / "_skills.py").write_text(body)
    return tmp_path


def _findings(repo: Path) -> list[_StubViolation]:
    out: list[_StubViolation] = []
    check_skills_federation(repo, _StubViolation, out)
    return out


_HAND_ROLLED = '''"""scitex-demo skills. Self-contained. No scitex-dev runtime dep."""
import click

@click.group()
def skills():
    pass
'''

_FEDERATED = '''"""scitex-demo skills — federated."""
from scitex_dev.cli import skills_click_group

skills = skills_click_group(package="demo-pkg")
'''


# ===== rule FIRES =====


class TestPS217Fires:
    def test_hand_rolled_skills_fires(self, tmp_path: Path) -> None:
        # Arrange
        repo = _make_leaf_skills(tmp_path, _HAND_ROLLED)
        # Act
        out = _findings(repo)
        # Assert
        assert any(v.rule == "PS-217" for v in out)

    def test_finding_path_points_at_skills_file(self, tmp_path: Path) -> None:
        # Arrange
        repo = _make_leaf_skills(tmp_path, _HAND_ROLLED, pkg_name="my_pkg")
        # Act
        out = _findings(repo)
        # Assert
        assert any(
            v.rule == "PS-217" and v.where.endswith("src/my_pkg/_cli/_skills.py")
            for v in out
        )


# ===== rule DOES NOT FIRE =====


class TestPS217DoesNotFire:
    def test_federated_leaf_no_fire(self, tmp_path: Path) -> None:
        # Arrange — leaf imports the shared primitive.
        repo = _make_leaf_skills(tmp_path, _FEDERATED)
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-217" for v in out)

    def test_no_skills_file_no_fire(self, tmp_path: Path) -> None:
        # Arrange — package with a _cli/ dir but no _skills.py.
        (tmp_path / "src" / "demo_pkg" / "_cli").mkdir(parents=True)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert not any(v.rule == "PS-217" for v in out)

    def test_no_src_dir_no_fire(self, tmp_path: Path) -> None:
        # Arrange — empty repo, no src/.
        # Act
        out = _findings(tmp_path)
        # Assert
        assert not any(v.rule == "PS-217" for v in out)


# ===== dep-free trio carve-out =====
#
# The rule text always said the trio (todo/sac/cct) is out of scope, but
# the exemption was never implemented, so a hand-rolled `_skills.py` in
# those packages was flagged anyway. Federating them is FORBIDDEN — they
# must not import scitex-dev — so the finding was unactionable by
# construction and inflated the reported PS-217 debt.


class TestPS217DepFreeTrioExempt:
    def test_scitex_cards_hand_rolled_no_fire(self, tmp_path: Path) -> None:
        # Arrange — todo/cards ships the hand-rolled shape by design.
        repo = _make_leaf_skills(tmp_path, _HAND_ROLLED, pkg_name="scitex_cards")
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-217" for v in out)

    def test_sac_hand_rolled_no_fire(self, tmp_path: Path) -> None:
        # Arrange
        repo = _make_leaf_skills(
            tmp_path, _HAND_ROLLED, pkg_name="scitex_agent_container"
        )
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-217" for v in out)

    def test_cct_hand_rolled_no_fire(self, tmp_path: Path) -> None:
        # Arrange
        repo = _make_leaf_skills(
            tmp_path, _HAND_ROLLED, pkg_name="claude_code_telegrammer"
        )
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-217" for v in out)

    def test_non_trio_package_still_fires(self, tmp_path: Path) -> None:
        # Arrange — guard against the carve-out over-matching.
        repo = _make_leaf_skills(tmp_path, _HAND_ROLLED, pkg_name="scitex_io")
        # Act
        out = _findings(repo)
        # Assert
        assert any(v.rule == "PS-217" for v in out)
