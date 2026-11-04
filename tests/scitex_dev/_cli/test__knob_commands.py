#!/usr/bin/env python3
"""CLI tests for `scitex-dev skills|mcp {status,enable,disable}`.

The knob state file is redirected via SCITEX_DEV_KNOB_STATE (env isolation,
no mocks); each invocation writes to a per-test tmp file.
"""

from __future__ import annotations

import json

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev._cli._cli_providers import register_cli_provider_commands
from scitex_dev._cli._knob_commands import add_knob_commands
from scitex_dev._core.config import _load_knob_state


def test_mcp_enable_persists_true(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main,
        ["mcp", "enable", "scitex-io"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert _load_knob_state(state)["mcp"]["scitex-io"] is True


def test_mcp_disable_persists_false(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main,
        ["mcp", "disable", "scitex-io"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert _load_knob_state(state)["mcp"]["scitex-io"] is False


def test_skills_enable_persists_true(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main,
        ["skills", "enable", "scitex-io"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert _load_knob_state(state)["skills"]["scitex-io"] is True


def test_skills_disable_persists_false(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main,
        ["skills", "disable", "scitex-io"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert _load_knob_state(state)["skills"]["scitex-io"] is False


def test_mcp_enable_exits_zero(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    result = CliRunner().invoke(
        main,
        ["mcp", "enable", "scitex-io"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert result.exit_code == 0


def test_mcp_status_exits_zero(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    result = CliRunner().invoke(
        main,
        ["mcp", "status"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert result.exit_code == 0


def test_skills_status_exits_zero(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    result = CliRunner().invoke(
        main,
        ["skills", "status"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert result.exit_code == 0


def test_skills_status_json_exits_zero(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    result = CliRunner().invoke(
        main,
        ["skills", "status", "--json"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert result.exit_code == 0


def test_mcp_disable_dry_run_leaves_state_unwritten(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main,
        ["mcp", "disable", "scitex-io", "--dry-run"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert not state.exists()


def test_skills_enable_dry_run_leaves_state_unwritten(tmp_path):
    # Arrange
    state = tmp_path / "ks.json"
    # Act
    CliRunner().invoke(
        main,
        ["skills", "enable", "scitex-io", "--dry-run"],
        env={"SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert not state.exists()


# EOF


@pytest.mark.parametrize("kind", ["cli", "mcp", "skills"])
def test_actual_cli_controls_include_unknown_owner_and_preserve_other_fields(
    tmp_path, kind
):
    # Arrange
    config = tmp_path / "config.yaml"
    config.write_text("packages: []\n")
    state = tmp_path / "knobs.json"
    state.write_text('{"cli":{},"mcp":{},"skills":{}}')
    group = click.Group()
    add_knob_commands(group, kind)
    env = {"SCITEX_DEV_CONFIG": str(config), "SCITEX_DEV_KNOB_STATE": str(state)}
    runner = CliRunner()
    # Act
    disabled = runner.invoke(group, ["disable", "unregistered-leaf", "--yes"], env=env)
    status = runner.invoke(group, ["status", "--json"], env=env)
    actual = json.loads(state.read_text())
    # Assert
    assert (
        disabled.exit_code,
        status.exit_code,
        json.loads(status.stdout)["unregistered-leaf"],
        actual[kind]["unregistered-leaf"],
        [actual[other] for other in ("cli", "mcp", "skills") if other != kind],
    ) == (0, 0, False, False, [{}, {}])


def test_cli_group_registers_real_status_enable_disable(tmp_path):
    # Arrange
    root = click.Group()
    group = register_cli_provider_commands(root)
    config, state = tmp_path / "config.yaml", tmp_path / "state.json"
    config.write_text("packages: []\n")
    env = {"SCITEX_DEV_CONFIG": str(config), "SCITEX_DEV_KNOB_STATE": str(state)}
    runner = CliRunner()
    # Act
    enabled = runner.invoke(
        root, ["cli", "enable", "unregistered-leaf", "--yes"], env=env
    )
    status = runner.invoke(root, ["cli", "status", "--json"], env=env)
    # Assert
    assert (
        set(group.commands),
        enabled.exit_code,
        status.exit_code,
        json.loads(status.stdout)["unregistered-leaf"],
    ) == ({"list", "status", "enable", "disable"}, 0, 0, True)


def test_cli_malformed_state_refuses_without_overwrite(tmp_path):
    # Arrange
    config, state = tmp_path / "config.yaml", tmp_path / "state.json"
    config.write_text("packages: []\n")
    state.write_text('{"cli":{"owned":"false"}}')
    original = state.read_bytes()
    group = click.Group()
    add_knob_commands(group, "cli")
    # Act
    result = CliRunner().invoke(
        group,
        ["disable", "other", "--yes"],
        env={"SCITEX_DEV_CONFIG": str(config), "SCITEX_DEV_KNOB_STATE": str(state)},
    )
    # Assert
    assert (
        result.exit_code,
        "boolean" in result.output,
        state.read_bytes() == original,
    ) == (1, True, True)


def test_status_paths_reports_selected_files_without_raw_config(tmp_path):
    # Arrange
    config, state = tmp_path / "selected.yaml", tmp_path / "selected.json"
    config.write_text(
        "packages:\n  - name: unknown-leaf\n    cli_enabled: false\nignored_secret: PRIVATE_SENTINEL\n"
    )
    group = click.Group()
    add_knob_commands(group, "cli")
    # Act
    result = CliRunner().invoke(
        group,
        ["status", "--paths", "--json"],
        env={"SCITEX_DEV_CONFIG": str(config), "SCITEX_DEV_KNOB_STATE": str(state)},
    )
    data = json.loads(result.stdout)
    # Assert
    assert (
        result.exit_code,
        data["config_path"],
        data["knob_state_path"],
        data["preferences"]["unknown-leaf"],
        "PRIVATE_SENTINEL" in result.output,
    ) == (0, str(config), str(state), False, False)
