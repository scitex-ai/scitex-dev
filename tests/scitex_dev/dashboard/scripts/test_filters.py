"""Smoke test for scitex_dev.dashboard.scripts.filters."""

from scitex_dev.dashboard.scripts.filters import get_filters_js


def test_get_filters_js():
    # Arrange
    # Act
    # Assert
    js = get_filters_js()
    assert isinstance(js, str) and "renderFilters" in js
