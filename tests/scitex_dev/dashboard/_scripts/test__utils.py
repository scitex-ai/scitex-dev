"""Smoke test for scitex_dev.dashboard._scripts._utils."""

from scitex_dev.dashboard._scripts._utils import get_utils_js


def test_get_utils_js():
    js = get_utils_js()
    assert isinstance(js, str)
    assert "toggleCard" in js
