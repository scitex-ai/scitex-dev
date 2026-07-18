#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Version ordering. The contract: what it cannot parse, it refuses to judge."""

from __future__ import annotations

from scitex_dev.versioning._version import compare, is_behind, latest, parse


def test_orders_by_number_not_string():
    # Arrange
    older, newer = "0.21.9", "0.21.17"
    # Act
    result = compare(older, newer)
    # Assert
    assert result == -1


def test_tag_and_release_compare_equal():
    # Arrange
    tag, release = "v0.31.1", "0.31.1"
    # Act
    result = compare(tag, release)
    # Assert
    assert result == 0


def test_prerelease_sorts_before_final():
    # Arrange
    pre, final = "0.31.1rc1", "0.31.1"
    # Act
    result = compare(pre, final)
    # Assert
    assert result == -1


def test_unparseable_version_parses_to_none():
    # Arrange
    raw = "dev"
    # Act
    result = parse(raw)
    # Assert
    assert result is None


def test_compare_with_unparseable_is_none():
    # Arrange
    local = "0.0.0+unknown"
    # Act
    result = compare(local, "0.31.1")
    # Assert
    assert result is None


def test_older_install_is_behind():
    # Arrange
    installed, latest_ = "0.29.0", "0.31.0"
    # Act
    result = is_behind(installed, latest_)
    # Assert
    assert result is True


def test_equal_install_is_not_behind():
    # Arrange
    installed, latest_ = "0.31.0", "0.31.0"
    # Act
    result = is_behind(installed, latest_)
    # Assert
    assert result is False


def test_newer_install_is_not_behind():
    # Arrange
    installed, latest_ = "0.32.0", "0.31.0"
    # Act
    result = is_behind(installed, latest_)
    # Assert
    assert result is False


def test_behind_is_none_when_unparseable():
    # Arrange
    installed = "dev"
    # Act
    result = is_behind(installed, "0.31.0")
    # Assert
    assert result is None


def test_latest_picks_highest_release():
    # Arrange
    releases = ["0.21.4", "0.21.9", "0.29.0", "0.31.0", "0.21.11"]
    # Act
    result = latest(releases)
    # Assert
    assert result == "0.31.0"


def test_latest_skips_unparseable_entries():
    # Arrange
    releases = ["0.30.1", "not-a-version", "0.31.0"]
    # Act
    result = latest(releases)
    # Assert
    assert result == "0.31.0"


def test_latest_of_nothing_is_none():
    # Arrange
    releases: list[str] = []
    # Act
    result = latest(releases)
    # Assert
    assert result is None


# EOF
