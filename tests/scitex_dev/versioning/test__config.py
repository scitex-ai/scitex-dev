#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VersioningConfig: one object a leaf builds; everything sac hardcoded is a knob."""

from __future__ import annotations

import pytest

from scitex_dev.versioning._config import VersioningConfig


def test_module_defaults_from_dist():
    # Arrange
    cfg = VersioningConfig(dist="scitex-agent-container")
    # Act
    module = cfg.module
    # Assert
    assert module == "scitex_agent_container"


def test_pypi_url_defaults_from_dist():
    # Arrange
    cfg = VersioningConfig(dist="scitex-dev")
    # Act
    url = cfg.pypi_json_url
    # Assert
    assert url == "https://pypi.org/pypi/scitex-dev/json"


def test_env_prefix_derived_from_dist():
    # Arrange
    cfg = VersioningConfig(dist="scitex-agent-container")
    # Act
    prefix = cfg.env_prefix
    # Assert
    assert prefix == "SCITEX_AGENT_CONTAINER_FRESHNESS"


def test_two_leaves_get_distinct_cache_env():
    # Arrange
    a = VersioningConfig(dist="scitex-io")
    b = VersioningConfig(dist="scitex-dev")
    # Act
    collide = a.env_cache == b.env_cache
    # Assert
    assert collide is False


def test_cache_subpath_defaults_under_module():
    # Arrange
    cfg = VersioningConfig(dist="scitex-dev")
    # Act
    head = cfg.cache_subpath[0]
    # Assert
    assert head == "scitex_dev"


def test_explicit_env_prefix_is_respected():
    # Arrange
    cfg = VersioningConfig(dist="scitex-dev", env_prefix="MY_PREFIX")
    # Act
    quiet = cfg.env_quiet
    # Assert
    assert quiet == "MY_PREFIX_QUIET"


def test_empty_dist_is_rejected():
    # Arrange
    bad = "   "
    # Act
    # Assert
    with pytest.raises(ValueError):
        VersioningConfig(dist=bad)


# EOF
