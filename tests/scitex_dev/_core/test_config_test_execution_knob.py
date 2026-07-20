#!/usr/bin/env python3
"""Tests for the per-package test-execution MODE knob in config.py.

Mirrors the skills/mcp knob tests: the mode resolves ECOSYSTEM default →
config.yaml → knob-state.json, defaults to ``"local"``, and its setter writes
the machine-managed state file (never config.yaml). No mocks — an injectable
tmp state file is used throughout.
"""

from __future__ import annotations

from scitex_dev._core.config import (
    DevConfig,
    PackageConfig,
    _apply_knob_state,
    _load_knob_state,
    _parse_package_config,
    config_to_dict,
    get_test_execution_mode,
    set_package_test_execution,
)


def test_package_config_defaults_test_execution_local():
    # Arrange
    pkg = PackageConfig(name="scitex-io", local_path="", pypi_name="scitex-io")
    # Act
    value = pkg.test_execution
    # Assert
    assert value == "local"


def test_parse_package_config_reads_test_execution():
    # Arrange
    data = {"name": "scitex-io", "test_execution": "remote-required"}
    # Act
    pkg = _parse_package_config(data)
    # Assert
    assert pkg.test_execution == "remote-required"


def test_parse_package_config_defaults_test_execution_when_absent():
    # Arrange
    data = {"name": "scitex-io", "local_path": ""}
    # Act
    pkg = _parse_package_config(data)
    # Assert
    assert pkg.test_execution == "local"


def test_set_package_test_execution_persists_mode(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    # Act
    set_package_test_execution("scitex-io", "remote-required", path=state_file)
    # Assert
    assert (
        _load_knob_state(state_file)["test_execution"]["scitex-io"]
        == "remote-required"
    )


def test_set_package_test_execution_rejects_bad_mode(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    raised = False
    # Act
    try:
        set_package_test_execution("scitex-io", "bogus", path=state_file)
    except ValueError:
        raised = True
    # Assert
    assert raised is True


def test_apply_knob_state_overlays_test_execution(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    set_package_test_execution("scitex-io", "remote-required", path=state_file)
    packages = [PackageConfig("scitex-io", "", "scitex-io")]
    # Act
    _apply_knob_state(packages, path=state_file)
    # Assert
    assert packages[0].test_execution == "remote-required"


def test_apply_knob_state_leaves_test_execution_default_when_unlisted(tmp_path):
    # Arrange
    state_file = tmp_path / "knob-state.json"
    set_package_test_execution("scitex-io", "remote-required", path=state_file)
    packages = [PackageConfig("figrecipe", "", "figrecipe")]
    # Act
    _apply_knob_state(packages, path=state_file)
    # Assert
    assert packages[0].test_execution == "local"


def test_load_knob_state_includes_test_execution_section(tmp_path):
    # Arrange
    state_file = tmp_path / "absent.json"
    # Act
    state = _load_knob_state(state_file)
    # Assert
    assert state == {"skills": {}, "mcp": {}, "test_execution": {}}


def test_get_test_execution_mode_reads_resolved_package():
    # Arrange
    cfg = DevConfig(
        packages=[PackageConfig("scitex-io", "", "scitex-io", test_execution="remote-required")]
    )
    # Act
    mode = get_test_execution_mode("scitex-io", cfg)
    # Assert
    assert mode == "remote-required"


def test_get_test_execution_mode_unknown_defaults_local():
    # Arrange
    cfg = DevConfig(packages=[])
    # Act
    mode = get_test_execution_mode("nonexistent", cfg)
    # Assert
    assert mode == "local"


def test_config_to_dict_surfaces_test_execution_per_package():
    # Arrange
    cfg = DevConfig(
        packages=[PackageConfig("a", "", "a", test_execution="remote-required")]
    )
    # Act
    out = config_to_dict(cfg)
    # Assert
    assert out["packages"][0]["test_execution"] == "remote-required"


# EOF
