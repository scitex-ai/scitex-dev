"""Smoke tests for scitex_dev.plt (ported from umbrella)."""

import scitex_dev.plt as plt_mod


def test_plt_module_has_dunder_path():
    assert hasattr(plt_mod, "__path__")


def test_plt_subpackages_importable():
    import scitex_dev.plt.mpl  # noqa: F401
    import scitex_dev.plt.demo_plotters  # noqa: F401

    assert True
