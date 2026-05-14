"""Smoke test for scitex_dev.dashboard._scripts._utils."""

from scitex_dev.dashboard._scripts._utils import get_utils_js


def test_get_utils_js_isinstance_js_str():
    # Arrange
    # Act
    # Assert
    js = get_utils_js()
    assert isinstance(js, str)


def test_get_utils_js_togglecard_in_js():
    # Arrange
    # Act
    # Assert
    js = get_utils_js()
    assert "toggleCard" in js
