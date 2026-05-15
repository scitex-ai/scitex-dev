"""Tests for scitex_dev._branding.__init__ re-exports."""

from __future__ import annotations

import scitex_dev._branding as branding


def test_init_reexports_get():
    # Arrange
    mod = branding
    # Act
    obj = mod.get
    # Assert
    assert callable(obj)


def test_init_reexports_get_brand():
    # Arrange
    mod = branding
    # Act
    obj = mod.get_brand
    # Assert
    assert callable(obj)


def test_init_reexports_get_env():
    # Arrange
    mod = branding
    # Act
    obj = mod.get_env
    # Assert
    assert callable(obj)


def test_init_reexports_iter_brands():
    # Arrange
    mod = branding
    # Act
    obj = mod.iter_brands
    # Assert
    assert callable(obj)


def test_init_reexports_register_method_aliases():
    # Arrange
    mod = branding
    # Act
    obj = mod.register_method_aliases
    # Assert
    assert callable(obj)


def test_init_reexports_translate():
    # Arrange
    mod = branding
    # Act
    obj = mod.translate
    # Assert
    assert callable(obj)


def test_init_reexports_brand_type():
    # Arrange
    mod = branding
    # Act
    has_brand = hasattr(mod, "Brand")
    # Assert
    assert has_brand


def test_init___all___declares_public_names():
    # Arrange
    expected = {
        "Brand",
        "get",
        "get_brand",
        "get_env",
        "iter_brands",
        "register_method_aliases",
        "translate",
    }
    # Act
    actual = set(branding.__all__)
    # Assert
    assert actual == expected
