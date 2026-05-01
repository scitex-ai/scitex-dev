"""Smoke test for scitex_dev.dashboard._scripts._render."""

from scitex_dev.dashboard._scripts._render import get_render_js


def test_get_render_js():
    js = get_render_js()
    assert isinstance(js, str)
    assert "renderData" in js
