"""Smoke test for scitex_dev.dashboard.scripts — public aggregator."""

from __future__ import annotations


def test_scripts_get_javascript_aggregates_isinstance_js_str():
    # Arrange
    # Act
    # Assert
    from scitex_dev.dashboard.scripts import get_javascript

    js = get_javascript()
    assert isinstance(js, str)


def test_scripts_get_javascript_aggregates_fetchversions_in_js():
    # Arrange
    # Act
    # Assert
    from scitex_dev.dashboard.scripts import get_javascript

    js = get_javascript()
    assert "fetchVersions" in js


def test_scripts_get_javascript_aggregates_renderdata_in_js():
    # Arrange
    # Act
    # Assert
    from scitex_dev.dashboard.scripts import get_javascript

    js = get_javascript()
    assert "renderData" in js
