"""Smoke test for scitex_dev.dashboard._scripts._filters."""

from scitex_dev.dashboard._scripts._filters import get_filters_js


def test_get_filters_js():
    js = get_filters_js()
    assert isinstance(js, str)
    assert "renderFilters" in js
