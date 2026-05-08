"""Smoke tests for scitex_dev.cv (ported from umbrella)."""

import pytest

pytest.importorskip("numpy")
pytest.importorskip("matplotlib")

import scitex_dev.cv as cv_mod  # noqa: E402


def test_cv_module_loads():
    assert hasattr(cv_mod, "_compose") or hasattr(cv_mod, "compose")


def test_cv_title_card_importable():
    from scitex_dev.cv import _title_card

    assert _title_card is not None
