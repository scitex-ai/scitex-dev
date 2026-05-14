"""Smoke test for scitex_dev.dashboard._scripts._cards."""

from scitex_dev.dashboard._scripts._cards import get_cards_js


def test_get_cards_js_isinstance_js_str():
    # Arrange
    # Act
    # Assert
    js = get_cards_js()
    assert isinstance(js, str)


def test_get_cards_js_renderworktreestatus_in_js():
    # Arrange
    # Act
    # Assert
    js = get_cards_js()
    assert "renderWorktreeStatus" in js
