#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the umbrella-MCP mount policy (``is_mcp_mountable`` / ``mountable_peers``).

The umbrella aggregator (``scitex._mcp.register_all_tools``) consults these
helpers as the single source of truth for which ecosystem peers it may
auto-mount onto ``scitex serve`` / ``scitex-mcp-server``. The canonical
exclusion is ``scitex-orochi`` — the single-instance agent-communication
orchestrator, which must never be mounted as a per-agent tool provider.
"""

from __future__ import annotations

from scitex_dev._ecosystem._core import (
    ECOSYSTEM,
    is_mcp_mountable,
    mountable_peers,
)


def test_orochi_orchestrator_is_not_mcp_mountable():
    # Arrange
    package = "scitex-orochi"
    # Act
    mountable = is_mcp_mountable(package)
    # Assert
    assert mountable is False


def test_orochi_absent_from_mountable_peers_list():
    # Arrange
    package = "scitex-orochi"
    # Act
    peers = mountable_peers()
    # Assert
    assert package not in peers


def test_types_zero_tool_peer_is_not_mcp_mountable():
    # Arrange
    package = "scitex-types"  # ships no _mcp_server; heavy import, zero tools
    # Act
    mountable = is_mcp_mountable(package)
    # Assert
    assert mountable is False


def test_str_zero_tool_peer_is_not_mcp_mountable():
    # Arrange
    package = "scitex-str"  # ships no _mcp server; pulls pandas/numpy, zero tools
    # Act
    mountable = is_mcp_mountable(package)
    # Assert
    assert mountable is False


def test_str_absent_from_mountable_peers_list():
    # Arrange
    package = "scitex-str"
    # Act
    peers = mountable_peers()
    # Assert
    assert package not in peers


def test_resource_tool_peer_stays_mcp_mountable():
    # Arrange
    package = "scitex-resource"  # ships real tools; font-cache fixed at source
    # Act
    mountable = is_mcp_mountable(package)
    # Assert
    assert mountable is True


def test_ordinary_library_peer_is_mcp_mountable():
    # Arrange
    package = "scitex-io"
    # Act
    mountable = is_mcp_mountable(package)
    # Assert
    assert mountable is True


def test_ordinary_library_present_in_mountable_peers():
    # Arrange
    package = "scitex-io"
    # Act
    peers = mountable_peers()
    # Assert
    assert package in peers


def test_umbrella_category_is_not_mcp_mountable():
    # Arrange
    package = "scitex"
    # Act
    mountable = is_mcp_mountable(package)
    # Assert
    assert mountable is False


def test_template_category_is_not_mcp_mountable():
    # Arrange
    package = "scitex-template"
    # Act
    mountable = is_mcp_mountable(package)
    # Assert
    assert mountable is False


def test_archived_peer_is_not_mcp_mountable():
    # Arrange
    package = "scitex-bridge"  # archived=True in the registry
    # Act
    mountable = is_mcp_mountable(package)
    # Assert
    assert mountable is False


def test_unknown_package_is_not_mcp_mountable():
    # Arrange
    package = "not-a-real-package"
    # Act
    mountable = is_mcp_mountable(package)
    # Assert
    assert mountable is False


def test_per_entry_mcp_mountable_false_field_excludes_peer():
    # Arrange
    package = "scitex-io"
    original = ECOSYSTEM[package]
    ECOSYSTEM[package] = {**original, "mcp_mountable": False}
    # Act
    try:
        mountable = is_mcp_mountable(package)
    finally:
        ECOSYSTEM[package] = original
    # Assert
    assert mountable is False


def test_mountable_peers_preserves_registry_insertion_order():
    # Arrange
    peers = mountable_peers()
    selected = set(peers)
    # Act
    registry_order = [p for p in ECOSYSTEM if p in selected]
    # Assert
    assert peers == registry_order


def test_mountable_peers_are_all_individually_mountable():
    # Arrange
    peers = mountable_peers()
    # Act
    all_mountable = all(is_mcp_mountable(p) for p in peers)
    # Assert
    assert all_mountable


def test_mountable_peers_list_is_non_empty():
    # Arrange / (no external state)
    # Act
    peers = mountable_peers()
    # Assert
    assert peers
