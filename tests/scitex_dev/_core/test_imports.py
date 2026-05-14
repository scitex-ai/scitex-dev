"""Tests for `scitex_dev._imports.try_import_optional`."""

from __future__ import annotations

from scitex_dev import (
    InstallHint,
    last_install_hint,
    try_import_optional,
)


def test_success_returns_module_mod_is_not_none():
    # Arrange
    # Act
    # Assert
    mod = try_import_optional("json")
    assert mod is not None


def test_success_returns_module_mod___name___json():
    # Arrange
    # Act
    # Assert
    mod = try_import_optional("json")
    assert mod.__name__ == "json"


def test_success_with_attr_jsondecoder_is_not_none():
    # Arrange
    # Act
    # Assert
    JSONDecoder = try_import_optional("json", attr="JSONDecoder")
    assert JSONDecoder is not None


def test_success_with_attr_jsondecoder___name___jsondecoder():
    # Arrange
    # Act
    # Assert
    JSONDecoder = try_import_optional("json", attr="JSONDecoder")
    assert JSONDecoder.__name__ == "JSONDecoder"


def test_failure_returns_none():
    # Arrange
    # Act
    # Assert
    obj = try_import_optional("definitely_not_a_real_module_xyz_zzz")
    assert obj is None


def test_failure_records_install_hint_isinstance_hint_installhint():
    # Arrange
    # Act
    # Assert
    name = "definitely_not_a_real_module_xyz_zzz_2"
    try_import_optional(name, extra="hdf5", pkg="scitex-io")
    hint = last_install_hint(name)
    assert isinstance(hint, InstallHint)


def test_failure_records_install_hint_hint_module_name():
    # Arrange
    # Act
    # Assert
    name = "definitely_not_a_real_module_xyz_zzz_2"
    try_import_optional(name, extra="hdf5", pkg="scitex-io")
    hint = last_install_hint(name)
    assert hint.module == name


def test_failure_records_install_hint_hint_extra_hdf5():
    # Arrange
    # Act
    # Assert
    name = "definitely_not_a_real_module_xyz_zzz_2"
    try_import_optional(name, extra="hdf5", pkg="scitex-io")
    hint = last_install_hint(name)
    assert hint.extra == "hdf5"


def test_failure_records_install_hint_hint_pkg_scitex_io():
    # Arrange
    # Act
    # Assert
    name = "definitely_not_a_real_module_xyz_zzz_2"
    try_import_optional(name, extra="hdf5", pkg="scitex-io")
    hint = last_install_hint(name)
    assert hint.pkg == "scitex-io"


def test_failure_records_install_hint_scitex_io_hdf5_in_hint_message():
    # Arrange
    # Act
    # Assert
    name = "definitely_not_a_real_module_xyz_zzz_2"
    try_import_optional(name, extra="hdf5", pkg="scitex-io")
    hint = last_install_hint(name)
    assert "scitex-io[hdf5]" in hint.message()


def test_missing_attr_returns_none_and_records_hint_obj_is_none():
    # Arrange
    # Act
    # Assert
    obj = try_import_optional("json", attr="not_a_real_attr", extra="x")
    assert obj is None
    hint = last_install_hint("json")


def test_missing_attr_returns_none_and_records_hint_hint_is_not_none_and_hint_extra_x():
    # Arrange
    # Act
    # Assert
    obj = try_import_optional("json", attr="not_a_real_attr", extra="x")
    hint = last_install_hint("json")
    assert hint is not None and hint.extra == "x"


def test_relative_import_requires_package():
    # Arrange
    # Act
    # Assert
    import pytest

    with pytest.raises(ValueError):
        try_import_optional(".sub")


def test_relative_import_resolves_with_package_obj_is_not_none():
    # `os.path` is importable as a relative submodule of `os`.
    # Arrange
    # Act
    # Assert
    obj = try_import_optional(".path", package="os")
    assert obj is not None


def test_relative_import_resolves_with_package_obj___name___in_posixpath_ntpath():
    # `os.path` is importable as a relative submodule of `os`.
    # Arrange
    # Act
    # Assert
    obj = try_import_optional(".path", package="os")
    assert obj.__name__ in {"posixpath", "ntpath"}


def test_install_hint_message_variants_installhint_module_m_extra_none_pkg_none():
    # Arrange
    # Act
    # Assert
    assert (
        InstallHint(module="m", extra=None, pkg=None).message()
        == "`m` is required. Install with: pip install m"
    )


def test_install_hint_message_variants_the_x_extra_in_installhint_module_m_extr():
    # Arrange
    # Act
    # Assert
    assert "the 'x' extra" in InstallHint(module="m", extra="x", pkg=None).message()


def test_install_hint_message_variants_p_x_in_installhint_module_m_extra_x_pkg():
    # Arrange
    # Act
    # Assert
    assert "p[x]" in InstallHint(module="m", extra="x", pkg="p").message()
