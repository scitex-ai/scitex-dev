#!/usr/bin/env python3
"""Tests for the machine-managed knob-state persistence layer.

The CLI/aggregators toggle a package's skills/mcp knob via `set_package_knob`,
which writes a dedicated JSON state file — the hand-authored config.yaml is
never rewritten. Persistence functions take an injectable `path`, so these
tests use a real tmp file (no mocks, no env).
"""

from __future__ import annotations

from scitex_dev._core.config import (
    DevConfig,
    PackageConfig,
    _apply_knob_state,
    _load_knob_state,
    set_package_knob,
)


def test_set_package_knob_persists_skills_disabled(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    # Act
    set_package_knob("scitex-io", "skills", False, path=state_file)
    # Assert
    assert _load_knob_state(state_file)["skills"]["scitex-io"] is False


def test_set_package_knob_persists_mcp_disabled(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    # Act
    set_package_knob("scitex-io", "mcp", False, path=state_file)
    # Assert
    assert _load_knob_state(state_file)["mcp"]["scitex-io"] is False


def test_set_package_knob_rejects_unknown_kind(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    # Act
    raised = False
    try:
        set_package_knob("scitex-io", "bogus", False, path=state_file)
    except ValueError:
        raised = True
    # Assert
    assert raised is True


def test_load_knob_state_returns_empty_when_file_absent(tmp_path):
    # Arrange
    state_file = tmp_path / "does-not-exist.json"
    # Act
    state = _load_knob_state(state_file)
    # Assert
    assert state == {"skills": {}, "mcp": {}, "test_execution": {}}


def test_load_knob_state_tolerates_corrupt_file(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    state_file.write_text("{ not valid json")
    # Act
    state = _load_knob_state(state_file)
    # Assert
    assert state == {"skills": {}, "mcp": {}, "test_execution": {}}


def test_apply_knob_state_disables_skills_on_matching_package(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    set_package_knob("scitex-io", "skills", False, path=state_file)
    packages = [PackageConfig("scitex-io", "", "scitex-io")]
    # Act
    _apply_knob_state(packages, path=state_file)
    # Assert
    assert packages[0].skills_enabled is False


def test_apply_knob_state_disables_mcp_on_matching_package(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    set_package_knob("scitex-io", "mcp", False, path=state_file)
    packages = [PackageConfig("scitex-io", "", "scitex-io")]
    # Act
    _apply_knob_state(packages, path=state_file)
    # Assert
    assert packages[0].mcp_enabled is False


def test_apply_knob_state_leaves_unlisted_package_untouched(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    set_package_knob("scitex-io", "skills", False, path=state_file)
    packages = [PackageConfig("figrecipe", "", "figrecipe")]
    # Act
    _apply_knob_state(packages, path=state_file)
    # Assert
    assert packages[0].skills_enabled is True


def test_set_package_knob_returns_the_state_file_path(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    # Act
    returned = set_package_knob("scitex-io", "skills", True, path=state_file)
    # Assert
    assert returned == state_file


def test_set_package_knob_re_enable_overwrites_prior_disable(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    set_package_knob("scitex-io", "skills", False, path=state_file)
    # Act
    set_package_knob("scitex-io", "skills", True, path=state_file)
    # Assert
    assert _load_knob_state(state_file)["skills"]["scitex-io"] is True


# EOF
