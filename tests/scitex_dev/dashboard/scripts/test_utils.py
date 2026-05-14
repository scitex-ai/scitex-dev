"""Smoke test for scitex_dev.dashboard.scripts.utils."""

from scitex_dev.dashboard.scripts.utils import get_utils_js


def test_get_utils_js():
    # Arrange
    # Act
    # Assert
    js = get_utils_js()
    assert isinstance(js, str) and "toggleCard" in js
