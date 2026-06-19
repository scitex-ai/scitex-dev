"""Mirror tests for `_checks/_discovery.py` — package-resolution helpers.

`_import_name` is pure string canonicalisation; `_locate_init` resolves an
installed package first, then the ecosystem-registry source tree. No mocks —
the installed `scitex_dev` package is the real positive fixture and a
nonexistent distribution is the real negative.
"""

from __future__ import annotations

from scitex_dev._cli.audit._api._checks._discovery import (
    _import_name,
    _locate_init,
)


def test_import_name_converts_hyphens_to_underscores():
    # Arrange
    # Act
    # Assert
    assert _import_name("scitex-io") == "scitex_io"


def test_import_name_leaves_plain_name_unchanged():
    # Arrange
    # Act
    # Assert
    assert _import_name("scitex") == "scitex"


def test_locate_init_finds_installed_package_init():
    # Arrange
    # Act
    # Assert
    result = _locate_init("scitex-dev", "scitex_dev")
    assert result is not None and result.name == "__init__.py"


def test_locate_init_returns_none_for_unknown_distribution():
    # Arrange
    # Act
    # Assert
    assert _locate_init("scitex-nope-nowhere", "scitex_nope_nowhere") is None
