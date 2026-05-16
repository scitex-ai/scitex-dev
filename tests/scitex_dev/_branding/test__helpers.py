"""Tests for scitex_dev._branding._helpers (real registry, no mocks).

Exercises the actual ``registry.yaml`` shipped with scitex-dev and the
real helpers in ``scitex_dev._branding._helpers``.
"""

from __future__ import annotations

import os

import pytest

from scitex_dev._branding import (
    get,
    get_brand,
    get_env,
    iter_brands,
    register_method_aliases,
    translate,
)


# ── env_isolated fixture (replaces monkeypatch) ─────────────────────────────


@pytest.fixture
def env_isolated():
    """Yield-fixture that snapshots branding-related env vars and restores."""
    keys = (
        "SOCIALIA_X_KEY",
        "SCITEX_X_KEY",
        "X_KEY",
        "SOCIALIA_MISSING",
        "SCITEX_MISSING",
        "MISSING",
    )
    snapshot = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    yield os.environ
    for k, v in snapshot.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ── get / get_brand ─────────────────────────────────────────────────────────


def test_get_returns_alias_for_figrecipe():
    # Arrange
    brand = "figrecipe"
    # Act
    alias = get(brand, "alias")
    # Assert
    assert alias == "fr"


def test_get_returns_umbrella_attr_for_scitex_plt():
    # Arrange
    brand = "scitex-plt"
    # Act
    value = get(brand, "umbrella_attr")
    # Assert
    assert value == "scitex.plt"


def test_get_returns_env_prefix_for_socialia():
    # Arrange
    brand = "socialia"
    # Act
    value = get(brand, "env_prefix")
    # Assert
    assert value == "SOCIALIA"


def test_get_unknown_brand_raises():
    # Arrange
    bad_brand = "not-a-real-brand"
    raised = None
    # Act
    try:
        get(bad_brand, "alias")
    except KeyError as exc:
        raised = exc
    # Assert
    assert isinstance(raised, KeyError)


def test_get_unknown_field_raises():
    # Arrange
    brand = "figrecipe"
    raised = None
    # Act
    try:
        get(brand, "no_such_field")
    except KeyError as exc:
        raised = exc
    # Assert
    assert isinstance(raised, KeyError)


def test_get_brand_returns_figrecipe_method_prefix():
    # Arrange
    brand = "figrecipe"
    # Act
    entry = get_brand(brand)
    # Assert
    assert entry["method_prefix"] == "fr_"


def test_get_brand_returns_figrecipe_umbrella_brand():
    # Arrange
    brand = "figrecipe"
    # Act
    entry = get_brand(brand)
    # Assert
    assert entry["umbrella_brand"] == "scitex-plt"


def test_iter_brands_lists_all_four_keys():
    # Arrange
    expected = {"figrecipe", "scitex-plt", "socialia", "scitex-social"}
    # Act
    keys = {k for k, _ in iter_brands()}
    # Assert
    assert keys == expected


# ── translate ──────────────────────────────────────────────────────────────


def test_translate_native_to_umbrella():
    # Arrange
    name = "fr_conf_mat"
    # Act
    result = translate(name, from_brand="figrecipe", to_brand="scitex-plt")
    # Assert
    assert result == "stx_conf_mat"


def test_translate_umbrella_to_native():
    # Arrange
    name = "stx_conf_mat"
    # Act
    result = translate(name, from_brand="scitex-plt", to_brand="figrecipe")
    # Assert
    assert result == "fr_conf_mat"


def test_translate_non_counterpart_raises():
    # Arrange: pick a name that should not translate cross-brand.
    name = "fr_x"
    captured = None
    # Act: attempt an illegal cross-brand translation and capture the error.
    try:
        translate(name, from_brand="figrecipe", to_brand="socialia")
    except ValueError as exc:
        captured = exc
    # Assert: a ValueError was raised.
    assert isinstance(captured, ValueError)


def test_translate_wrong_prefix_raises():
    # Arrange: a name lacking the source brand's method_prefix.
    name = "plot"
    captured = None
    # Act: attempt a translation that must reject the unprefixed name.
    try:
        translate(name, from_brand="figrecipe", to_brand="scitex-plt")
    except ValueError as exc:
        captured = exc
    # Assert: a ValueError was raised.
    assert isinstance(captured, ValueError)


# ── register_method_aliases ─────────────────────────────────────────────────


def _make_stx_demo_class():
    """Helper: build a fresh class with stx_* methods for each test."""

    class Demo:
        def stx_plot(self, x):
            """Stx plot doc."""
            return ("plot", x)

        def stx_heat(self, m):
            return ("heat", m)

    return Demo


def test_register_method_aliases_binds_fr_plot():
    # Arrange
    cls = _make_stx_demo_class()
    # Act
    register_method_aliases(cls, brand_key="scitex-plt")
    # Assert
    assert hasattr(cls, "fr_plot")


def test_register_method_aliases_alias_callable_returns_same_result():
    # Arrange
    cls = _make_stx_demo_class()
    register_method_aliases(cls, brand_key="scitex-plt")
    instance = cls()
    # Act
    result = instance.fr_plot(7)
    # Assert
    assert result == ("plot", 7)


def test_register_method_aliases_alias_module_is_native_import_name():
    # Arrange
    cls = _make_stx_demo_class()
    # Act
    register_method_aliases(cls, brand_key="scitex-plt")
    # Assert
    assert cls.fr_plot.__module__ == "figrecipe"


def test_register_method_aliases_original_module_untouched():
    # Arrange
    cls = _make_stx_demo_class()
    pre_module = cls.stx_plot.__module__
    # Act
    register_method_aliases(cls, brand_key="scitex-plt")
    # Assert
    assert cls.stx_plot.__module__ == pre_module


def test_register_method_aliases_umbrella_module_for_native_side():
    # Arrange
    class Demo:
        def fr_plot(self, x):
            return x

    # Act
    register_method_aliases(Demo, brand_key="figrecipe")
    # Assert
    assert Demo.stx_plot.__module__ == "scitex.plt"


def test_register_method_aliases_noop_without_method_prefix():
    # Arrange
    class Demo:
        def fr_plot(self):
            return 1

    # Act
    register_method_aliases(Demo, brand_key="scitex-social")
    # Assert
    assert not hasattr(Demo, "stx_plot")


# ── get_env ────────────────────────────────────────────────────────────────


def test_get_env_primary_prefix(env_isolated):
    # Arrange
    env_isolated["SOCIALIA_X_KEY"] = "primary"
    # Act
    value = get_env("X_KEY", brand_key="socialia")
    # Assert
    assert value == "primary"


def test_get_env_counterpart_prefix(env_isolated):
    # Arrange
    env_isolated["SCITEX_X_KEY"] = "from-scitex"
    # Act
    value = get_env("X_KEY", brand_key="socialia")
    # Assert
    assert value == "from-scitex"


def test_get_env_falls_back_to_unprefixed(env_isolated):
    # Arrange
    env_isolated["X_KEY"] = "plain"
    # Act
    value = get_env("X_KEY", brand_key="socialia")
    # Assert
    assert value == "plain"


def test_get_env_default(env_isolated):
    # Arrange
    # (no env vars set — env_isolated already cleared them)
    # Act
    value = get_env("MISSING", brand_key="socialia", default="d")
    # Assert
    assert value == "d"
