"""Smoke test for scitex_dev.dashboard._scripts._render."""

from scitex_dev.dashboard._scripts._render import get_render_js


def test_get_render_js_isinstance_js_str():
    # Arrange
    # Act
    # Assert
    js = get_render_js()
    assert isinstance(js, str)


def test_get_render_js_renderdata_in_js():
    # Arrange
    # Act
    # Assert
    js = get_render_js()
    assert "renderData" in js
