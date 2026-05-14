"""Smoke test for scitex_dev.dashboard._scripts._core."""

from scitex_dev.dashboard._scripts._core import get_core_js


def test_get_core_js_isinstance_js_str():
    # Arrange
    # Act
    # Assert
    js = get_core_js()
    assert isinstance(js, str)


def test_get_core_js_fetchversions_in_js():
    # Arrange
    # Act
    # Assert
    js = get_core_js()
    assert "fetchVersions" in js
