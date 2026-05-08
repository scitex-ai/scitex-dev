"""Smoke tests for scitex_dev.plt.demo_plotters."""

import scitex_dev.plt.demo_plotters as dp_mod


def test_demo_plotters_module_loads():
    assert hasattr(dp_mod, "__path__")
