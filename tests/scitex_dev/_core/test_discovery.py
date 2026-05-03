#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for _discovery module."""

from unittest.mock import MagicMock, patch

import pytest

from scitex_dev._core.discovery import (
    discover_packages,
    get_package_root,
    get_sphinx_source,
    invalidate_cache,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Ensure discovery cache is cleared between tests."""
    invalidate_cache()
    yield
    invalidate_cache()


class TestDiscoverPackages:
    def test_returns_dict(self):
        result = discover_packages()
        assert isinstance(result, dict)

    def test_caching(self):
        """Second call should return cached result."""
        result1 = discover_packages()
        result2 = discover_packages()
        assert result1 is result2  # Same object (cached)

    def test_invalidate_cache(self):
        result1 = discover_packages()
        invalidate_cache()
        result2 = discover_packages()
        assert result1 is not result2  # Different objects

    def test_with_mock_entry_points(self):
        ep = MagicMock()
        ep.name = "test-pkg"
        ep.value = "test_pkg"

        with (
            patch("importlib.metadata.entry_points", return_value=[ep]),
            patch("scitex_dev._core.discovery.ECOSYSTEM", {}, create=True),
            patch.dict(
                "sys.modules", {"scitex_dev._ecosystem": MagicMock(ECOSYSTEM={})}
            ),
        ):
            result = discover_packages()

        assert result == {"test-pkg": "test_pkg"}

    def test_handles_entry_point_error(self):
        """Should return empty dict on error, not raise."""
        with (
            patch("importlib.metadata.entry_points", side_effect=Exception("fail")),
            patch.dict(
                "sys.modules", {"scitex_dev._ecosystem": MagicMock(ECOSYSTEM={})}
            ),
        ):
            result = discover_packages()

        assert result == {}


class TestGetPackageRoot:
    def test_existing_package(self):
        # os is always available
        root = get_package_root("os")
        assert root is not None

    def test_nonexistent_package(self):
        result = get_package_root("nonexistent_package_xyz_123")
        assert result is None

    def test_package_with_path(self):
        root = get_package_root("json")
        assert root is not None


class TestGetSphinxSource:
    def test_nonexistent_package(self):
        result = get_sphinx_source("nonexistent_package_xyz_123")
        assert result is None

    def test_package_without_sphinx(self):
        # os module won't have sphinx docs
        result = get_sphinx_source("os")
        assert result is None
