#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for `scitex-dev skills|mcp {status,enable,disable}`.

The knob state file is redirected via SCITEX_DEV_KNOB_STATE (env isolation,
no mocks); each invocation writes to a per-test tmp file.
"""

from __future__ import annotations

from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev._core.config import _load_knob_state


def test_mcp_enable_persists_true(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main, ["mcp", "enable", "scitex-io"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert _load_knob_state(state)["mcp"]["scitex-io"] is True


def test_mcp_disable_persists_false(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main, ["mcp", "disable", "scitex-io"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert _load_knob_state(state)["mcp"]["scitex-io"] is False


def test_skills_enable_persists_true(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main, ["skills", "enable", "scitex-io"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert _load_knob_state(state)["skills"]["scitex-io"] is True


def test_skills_disable_persists_false(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main, ["skills", "disable", "scitex-io"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert _load_knob_state(state)["skills"]["scitex-io"] is False


def test_mcp_enable_exits_zero(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    result = CliRunner().invoke(
        main, ["mcp", "enable", "scitex-io"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert result.exit_code == 0


def test_mcp_status_exits_zero(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    result = CliRunner().invoke(
        main, ["mcp", "status"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert result.exit_code == 0


def test_skills_status_exits_zero(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    result = CliRunner().invoke(
        main, ["skills", "status"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert result.exit_code == 0


def test_skills_status_json_exits_zero(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    result = CliRunner().invoke(
        main, ["skills", "status", "--json"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert result.exit_code == 0


def test_mcp_disable_dry_run_leaves_state_unwritten(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main, ["mcp", "disable", "scitex-io", "--dry-run"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert not state.exists()


def test_skills_enable_dry_run_leaves_state_unwritten(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main, ["skills", "enable", "scitex-io", "--dry-run"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert not state.exists()


# EOF
