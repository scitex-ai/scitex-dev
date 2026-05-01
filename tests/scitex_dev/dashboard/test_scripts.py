"""Smoke test for scitex_dev.dashboard.scripts — public aggregator."""

from __future__ import annotations


def test_scripts_get_javascript_aggregates():
    from scitex_dev.dashboard.scripts import get_javascript

    js = get_javascript()
    assert isinstance(js, str)
    assert "fetchVersions" in js
    assert "renderData" in js
