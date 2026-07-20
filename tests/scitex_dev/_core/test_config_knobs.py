#!/usr/bin/env python3
"""Tests for the per-leaf skills/mcp progressive-disclosure knobs.

Operator directive 2026-07-20: each package carries a skills-enable and an
mcp-enable flag, centrally managed by scitex-dev, so the aggregators can scope
what loads into context. These tests pin the schema (default-on), the YAML
parse, and the resolved-view helpers.
"""

from __future__ import annotations

from scitex_dev._core.config import (
    DevConfig,
    PackageConfig,
    _parse_package_config,
    config_to_dict,
    get_enabled_mcp,
    get_enabled_skills,
)


def test_package_config_defaults_skills_enabled_true():
    # Arrange
    pkg = PackageConfig(name="scitex-io", local_path="", pypi_name="scitex-io")
    # Act
    value = pkg.skills_enabled
    # Assert
    assert value is True


def test_package_config_defaults_mcp_enabled_true():
    # Arrange
    pkg = PackageConfig(name="scitex-io", local_path="", pypi_name="scitex-io")
    # Act
    value = pkg.mcp_enabled
    # Assert
    assert value is True


def test_parse_package_config_reads_skills_disabled():
    # Arrange
    data = {"name": "scitex-io", "local_path": "", "skills_enabled": False}
    # Act
    pkg = _parse_package_config(data)
    # Assert
    assert pkg.skills_enabled is False


def test_parse_package_config_reads_mcp_disabled():
    # Arrange
    data = {"name": "scitex-io", "local_path": "", "mcp_enabled": False}
    # Act
    pkg = _parse_package_config(data)
    # Assert
    assert pkg.mcp_enabled is False


def test_parse_package_config_defaults_skills_true_when_absent():
    # Arrange
    data = {"name": "scitex-io", "local_path": ""}
    # Act
    pkg = _parse_package_config(data)
    # Assert
    assert pkg.skills_enabled is True


def test_parse_package_config_defaults_mcp_true_when_absent():
    # Arrange
    data = {"name": "scitex-io", "local_path": ""}
    # Act
    pkg = _parse_package_config(data)
    # Assert
    assert pkg.mcp_enabled is True


def test_get_enabled_skills_excludes_skills_disabled_package():
    # Arrange
    cfg = DevConfig(
        packages=[
            PackageConfig("a", "", "a", skills_enabled=True),
            PackageConfig("b", "", "b", skills_enabled=False),
        ]
    )
    # Act
    names = {p.name for p in get_enabled_skills(cfg)}
    # Assert
    assert names == {"a"}


def test_get_enabled_mcp_excludes_mcp_disabled_package():
    # Arrange
    cfg = DevConfig(
        packages=[
            PackageConfig("a", "", "a", mcp_enabled=False),
            PackageConfig("b", "", "b", mcp_enabled=True),
        ]
    )
    # Act
    names = {p.name for p in get_enabled_mcp(cfg)}
    # Assert
    assert names == {"b"}


def test_config_to_dict_surfaces_skills_knob_per_package():
    # Arrange
    cfg = DevConfig(packages=[PackageConfig("a", "", "a", skills_enabled=False)])
    # Act
    out = config_to_dict(cfg)
    # Assert
    assert out["packages"][0]["skills_enabled"] is False


def test_config_to_dict_surfaces_mcp_knob_per_package():
    # Arrange
    cfg = DevConfig(packages=[PackageConfig("a", "", "a", mcp_enabled=True)])
    # Act
    out = config_to_dict(cfg)
    # Assert
    assert out["packages"][0]["mcp_enabled"] is True


# EOF
