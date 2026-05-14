"""Smoke test for scitex_dev.dashboard.scripts.core."""

from scitex_dev.dashboard.scripts.core import get_core_js


def test_get_core_js():
    # Arrange
    # Act
    # Assert
    js = get_core_js()
    assert isinstance(js, str) and "fetchVersions" in js
