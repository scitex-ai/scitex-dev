"""Smoke test for scitex_dev.dashboard._scripts module re-export."""

from __future__ import annotations


def test__scripts_reexports_get_javascript():
    from scitex_dev.dashboard._scripts import get_javascript

    js = get_javascript()
    assert isinstance(js, str) and len(js) > 100
    # The aggregator wires up the auto-refresh tick.
    assert "fetchVersions" in js
