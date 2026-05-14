"""Smoke test for scitex_dev.dashboard._app — Flask factory builds an app."""

from __future__ import annotations

import pytest

pytest.importorskip("flask")


def test_create_app_returns_flask_app_app_is_not_none():
    # Arrange
    # Act
    # Assert
    from scitex_dev.dashboard._app import create_app

    app = create_app()
    assert app is not None
    rules = {r.rule for r in app.url_map.iter_rules()}


def test_create_app_returns_flask_app_in_rules():
    # Arrange
    # Act
    # Assert
    from scitex_dev.dashboard._app import create_app

    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/" in rules
