"""Smoke test for scitex_dev.dashboard._scripts._filters."""

from scitex_dev.dashboard._scripts._filters import get_filters_js


def test_get_filters_js_isinstance_js_str():
    # Arrange
    # Act
    # Assert
    js = get_filters_js()
    assert isinstance(js, str)


def test_get_filters_js_renderfilters_in_js():
    # Arrange
    # Act
    # Assert
    js = get_filters_js()
    assert "renderFilters" in js
