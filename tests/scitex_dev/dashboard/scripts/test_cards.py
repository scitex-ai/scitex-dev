"""Smoke test for scitex_dev.dashboard.scripts.cards."""

from scitex_dev.dashboard.scripts.cards import get_cards_js


def test_get_cards_js():
    # Arrange
    # Act
    # Assert
    js = get_cards_js()
    assert isinstance(js, str) and "renderWorktreeStatus" in js
