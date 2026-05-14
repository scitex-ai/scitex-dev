"""Smoke test for scitex_dev.dashboard.routes — register_routes imports and binds."""

from __future__ import annotations

import pytest

pytest.importorskip("flask")


def test_register_routes_attaches_endpoints_in_rules():
    # Arrange
    # Act
    # Assert
    from flask import Flask

    from scitex_dev.dashboard.routes import register_routes

    app = Flask(__name__)
    register_routes(app)
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/" in rules


def test_register_routes_attaches_endpoints_json_in_rules():
    # Arrange
    # Act
    # Assert
    from flask import Flask

    from scitex_dev.dashboard.routes import register_routes

    app = Flask(__name__)
    register_routes(app)
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/json" in rules
