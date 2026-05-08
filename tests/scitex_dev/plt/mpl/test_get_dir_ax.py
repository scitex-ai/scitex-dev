"""Smoke tests for scitex_dev.plt.mpl."""

import scitex_dev.plt.mpl as mpl_mod


def test_mpl_module_loads():
    assert hasattr(mpl_mod, "__path__")
