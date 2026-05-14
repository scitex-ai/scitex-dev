"""Smoke test for scitex_dev.dashboard.app — Flask factory builds an app."""

from __future__ import annotations

import pytest

pytest.importorskip("flask")


def test_create_app_returns_flask_app_app_is_not_none():
    # Arrange
    # Act
    # Assert
    from scitex_dev.dashboard.app import create_app

    app = create_app()
    assert app is not None
    # Has expected routes registered
    rules = {r.rule for r in app.url_map.iter_rules()}


def test_create_app_returns_flask_app_in_rules():
    # Arrange
    # Act
    # Assert
    from scitex_dev.dashboard.app import create_app

    app = create_app()
    # Has expected routes registered
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/" in rules


def test_create_app_returns_flask_app_json_in_rules_or_api_versions_in_rules():
    # Arrange
    # Act
    # Assert
    from scitex_dev.dashboard.app import create_app

    app = create_app()
    # Has expected routes registered
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/json" in rules or "/api/versions" in rules


def test_run_dashboard_callable_callable_run_dashboard():
    # Arrange
    # Act
    # Assert
    from scitex_dev.dashboard.app import run_dashboard, run_background, stop_dashboard

    assert callable(run_dashboard)


def test_run_dashboard_callable_callable_run_background():
    # Arrange
    # Act
    # Assert
    from scitex_dev.dashboard.app import run_dashboard, run_background, stop_dashboard

    assert callable(run_background)


def test_run_dashboard_callable_callable_stop_dashboard():
    # Arrange
    # Act
    # Assert
    from scitex_dev.dashboard.app import run_dashboard, run_background, stop_dashboard

    assert callable(stop_dashboard)
