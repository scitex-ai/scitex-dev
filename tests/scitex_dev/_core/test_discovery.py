#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for _discovery module."""

from dataclasses import dataclass

import pytest

from scitex_dev._core.discovery import (
    discover_packages,
    get_package_root,
    get_sphinx_source,
    invalidate_cache,
)


@dataclass
class _FakeEP:
    """Tiny stand-in for ``importlib.metadata.EntryPoint``."""

    name: str
    value: str


@pytest.fixture(autouse=True)
def clear_cache():
    """Ensure discovery cache is cleared between tests."""
    invalidate_cache()
    yield
    invalidate_cache()


class TestDiscoverPackages:
    def test_discover_packages_returns_dict_mapping(self):
        # Arrange
        # Act
        # Assert
        result = discover_packages()
        assert isinstance(result, dict)

    def test_repeated_calls_return_cached_object(self):
        """Second call should return cached result."""
        # Arrange
        # Act
        # Assert
        result1 = discover_packages()
        result2 = discover_packages()
        assert result1 is result2  # Same object (cached)

    def test_invalidate_cache_forces_fresh_discovery(self):
        # Arrange
        # Act
        # Assert
        result1 = discover_packages()
        invalidate_cache()
        result2 = discover_packages()
        assert result1 is not result2  # Different objects

    def test_with_injected_entry_points(self):
        """Injected entry_points_fn + empty ecosystem yields just the EP entries."""
        # Arrange
        # Act
        # Assert
        eps = [_FakeEP(name="test-pkg", value="test_pkg")]
        result = discover_packages(
            entry_points_fn=lambda group: eps,
            ecosystem={},
        )
        assert result == {"test-pkg": "test_pkg"}

    def test_handles_entry_point_error(self):
        """Should return empty dict on error, not raise."""

        # Arrange
        # Act
        # Assert
        def _raises(group):
            raise RuntimeError("simulated entry-points failure")

        result = discover_packages(entry_points_fn=_raises, ecosystem={})
        assert result == {}


class TestGetPackageRoot:
    def test_existing_package_returns_path(self):
        # os is always available
        # Arrange
        # Act
        # Assert
        root = get_package_root("os")
        assert root is not None

    def test_nonexistent_package_returns_none(self):
        # Arrange
        # Act
        # Assert
        result = get_package_root("nonexistent_package_xyz_123")
        assert result is None

    def test_package_with_path(self):
        # Arrange
        # Act
        # Assert
        root = get_package_root("json")
        assert root is not None


class TestGetSphinxSource:
    def test_nonexistent_package_returns_none(self):
        # Arrange
        # Act
        # Assert
        result = get_sphinx_source("nonexistent_package_xyz_123")
        assert result is None

    def test_package_without_sphinx(self):
        # os module won't have sphinx docs
        # Arrange
        # Act
        # Assert
        result = get_sphinx_source("os")
        assert result is None
