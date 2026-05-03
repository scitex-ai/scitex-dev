"""Tests for `scitex_dev._imports.try_import_optional`."""

from __future__ import annotations

from scitex_dev import (
    InstallHint,
    last_install_hint,
    try_import_optional,
)


def test_success_returns_module():
    mod = try_import_optional("json")
    assert mod is not None
    assert mod.__name__ == "json"


def test_success_with_attr():
    JSONDecoder = try_import_optional("json", attr="JSONDecoder")
    assert JSONDecoder is not None
    assert JSONDecoder.__name__ == "JSONDecoder"


def test_failure_returns_none():
    obj = try_import_optional("definitely_not_a_real_module_xyz_zzz")
    assert obj is None


def test_failure_records_install_hint():
    name = "definitely_not_a_real_module_xyz_zzz_2"
    try_import_optional(name, extra="hdf5", pkg="scitex-io")
    hint = last_install_hint(name)
    assert isinstance(hint, InstallHint)
    assert hint.module == name
    assert hint.extra == "hdf5"
    assert hint.pkg == "scitex-io"
    assert "scitex-io[hdf5]" in hint.message()


def test_missing_attr_returns_none_and_records_hint():
    obj = try_import_optional("json", attr="not_a_real_attr", extra="x")
    assert obj is None
    hint = last_install_hint("json")
    assert hint is not None and hint.extra == "x"


def test_relative_import_requires_package():
    import pytest

    with pytest.raises(ValueError):
        try_import_optional(".sub")


def test_relative_import_resolves_with_package():
    # `os.path` is importable as a relative submodule of `os`.
    obj = try_import_optional(".path", package="os")
    assert obj is not None
    assert obj.__name__ in {"posixpath", "ntpath"}


def test_install_hint_message_variants():
    assert (
        InstallHint(module="m", extra=None, pkg=None).message()
        == "`m` is required. Install with: pip install m"
    )
    assert "the 'x' extra" in InstallHint(module="m", extra="x", pkg=None).message()
    assert "p[x]" in InstallHint(module="m", extra="x", pkg="p").message()
