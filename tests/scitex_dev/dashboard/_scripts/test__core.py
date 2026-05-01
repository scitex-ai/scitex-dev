"""Smoke test for scitex_dev.dashboard._scripts._core."""

from scitex_dev.dashboard._scripts._core import get_core_js


def test_get_core_js():
    js = get_core_js()
    assert isinstance(js, str)
    assert "fetchVersions" in js
