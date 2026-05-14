"""Smoke test for scitex_dev.dashboard.scripts.render."""

from scitex_dev.dashboard.scripts.render import get_render_js


def test_get_render_js():
    # Arrange
    # Act
    # Assert
    js = get_render_js()
    assert isinstance(js, str) and "renderData" in js
