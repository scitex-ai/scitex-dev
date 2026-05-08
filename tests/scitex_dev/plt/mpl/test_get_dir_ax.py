"""Smoke tests for scitex_dev.plt.mpl."""

import pytest

pytest.importorskip("numpy")
pytest.importorskip("matplotlib")

import scitex_dev.plt.mpl as mpl_mod  # noqa: E402


def test_mpl_module_loads():
    assert hasattr(mpl_mod, "__path__")
