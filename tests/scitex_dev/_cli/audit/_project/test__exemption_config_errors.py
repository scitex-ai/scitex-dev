"""The shared `audit.exemptions` config-error arm.

Four checkers used to carry near-identical copies of this loop, and the copies
had drifted: three filtered with a bare `startswith("PS-22x")` (which DROPS
the block-level notice — the report of a silent drop) and PS-224 had no arm at
all. This suite pins the one implementation they now share.

No mocks (NM001-003): the config is a real value object with the attribute the
arm reads, and `emit` is a real closure collecting real tuples. Nothing is
patched.

One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from scitex_dev._cli.audit._config._exemptions import parse_exemptions
from scitex_dev._cli.audit._project._exemption_config_errors import (
    report_exemption_config_errors,
)


@dataclass(frozen=True)
class _Config:
    """The one attribute the arm reads — a real value, not a stand-in."""

    exemption_errors: tuple[str, ...]


def _notices(raw: object) -> tuple[str, ...]:
    """Real notices, produced by the real parser."""
    return parse_exemptions(raw)[1]


def _collect(repo: Path, config, rule: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    report_exemption_config_errors(
        repo, config, rule, lambda where, detail: found.append((where, detail))
    )
    return found


_BLOCK = _notices([{"rule": "PS-224", "path": "wf.yml::job", "reason": "x"}])
_ENTRY = _notices({"PS-220": [{"path": "a.py", "line": 1, "reason": ""}]})


def test_block_notice_is_reported_by_every_rule(tmp_path):
    # Arrange — a malformed block cost EVERY rule its exemptions.
    cfg = _Config(exemption_errors=_BLOCK)
    # Act
    found = [_collect(tmp_path, cfg, r) for r in ("PS-220", "PS-222", "PS-224")]
    # Assert
    assert [len(f) for f in found] == [1, 1, 1]


def test_entry_notice_is_reported_by_its_own_rule(tmp_path):
    # Arrange
    cfg = _Config(exemption_errors=_ENTRY)
    # Act
    found = _collect(tmp_path, cfg, "PS-220")
    # Assert
    assert len(found) == 1


def test_entry_notice_is_not_reported_by_another_rule(tmp_path):
    # Arrange — an entry-level rejection stays pinned to ONE rule.
    cfg = _Config(exemption_errors=_ENTRY)
    # Act
    found = _collect(tmp_path, cfg, "PS-224")
    # Assert
    assert found == []


def test_finding_points_at_the_config_file(tmp_path):
    # Arrange — the location must be the file the author edited.
    cfg = _Config(exemption_errors=_BLOCK)
    # Act
    found = _collect(tmp_path, cfg, "PS-224")
    # Assert
    assert found[0][0] == str(tmp_path / ".scitex/dev/config.yaml")


def test_block_detail_names_the_reporting_rule(tmp_path):
    # Arrange
    cfg = _Config(exemption_errors=_BLOCK)
    # Act
    found = _collect(tmp_path, cfg, "PS-224")
    # Assert
    assert "NO PS-224 exemption took effect" in found[0][1]


def test_block_detail_names_the_received_type(tmp_path):
    # Arrange
    cfg = _Config(exemption_errors=_BLOCK)
    # Act
    found = _collect(tmp_path, cfg, "PS-224")
    # Assert
    assert "got a list" in found[0][1]


@pytest.mark.parametrize("config", [None, _Config(exemption_errors=())])
def test_nothing_to_report_emits_nothing(tmp_path, config):
    # Arrange — POSITIVE CONTROL for silence: a clean config (and an absent
    # one) must produce no finding at all.
    # Act
    found = _collect(tmp_path, config, "PS-220")
    # Assert
    assert found == []


# EOF
