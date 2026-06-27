"""Tests for `scitex_dev._imports.try_import_optional`."""

from __future__ import annotations

import sys

import pytest

from scitex_dev import (
    InstallHint,
    last_install_hint,
    try_import_optional,
)


@pytest.fixture
def import_sandbox(tmp_path):
    """Yield a tmp dir on sys.path; restore sys.path + sys.modules after.

    Lets a test drop a REAL fake module that raises on import (no mocks) and
    leaves the interpreter's import state untouched afterward.
    """
    saved_path = list(sys.path)
    saved_mods = set(sys.modules)
    sys.path.insert(0, str(tmp_path))
    try:
        yield tmp_path
    finally:
        sys.path[:] = saved_path
        for name in set(sys.modules) - saved_mods:
            sys.modules.pop(name, None)


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


# ---------------------------------------------------------------------- #
# Present-but-broken optional dep (neurovista torch<->numpy ABI report)  #
# ---------------------------------------------------------------------- #


def test_broken_module_raising_runtimeerror_degrades_to_none(import_sandbox):
    # Arrange — a module that is PRESENT but raises RuntimeError on import.
    name = "abi_broken_mod_rt"
    (import_sandbox / f"{name}.py").write_text(
        "raise RuntimeError('boom at import')\n", encoding="utf-8"
    )
    # Act
    obj = try_import_optional(name)
    # Assert
    assert obj is None


def test_broken_module_records_real_cause_in_hint(import_sandbox):
    # Arrange
    name = "abi_broken_mod_cause"
    (import_sandbox / f"{name}.py").write_text(
        "raise RuntimeError('boom at import')\n", encoding="utf-8"
    )
    # Act
    try_import_optional(name)
    hint = last_install_hint(name)
    # Assert
    assert "RuntimeError: boom at import" in (hint.cause or "")


def test_numpy_abi_signature_yields_actionable_cause(import_sandbox):
    # Arrange — mimic the torch<->numpy ABI RuntimeError text.
    name = "abi_numpy_sig_mod"
    (import_sandbox / f"{name}.py").write_text(
        "raise RuntimeError('Failed to initialize NumPy: _ARRAY_API not found')\n",
        encoding="utf-8",
    )
    # Act
    try_import_optional(name)
    hint = last_install_hint(name)
    # Assert
    assert "numpy ABI mismatch" in (hint.cause or "")


def test_hint_message_includes_cause_when_present():
    # Arrange
    hint = InstallHint(module="m", extra=None, pkg=None, cause="RuntimeError: x")
    # Act
    msg = hint.message()
    # Assert
    assert "RuntimeError: x" in msg


def test_plain_missing_module_records_no_cause():
    # Arrange
    name = "definitely_absent_mod_no_cause_zzz"
    # Act
    try_import_optional(name, extra="x", pkg="p")
    hint = last_install_hint(name)
    # Assert
    assert hint.cause is None
