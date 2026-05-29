"""Tests for STX-I008 — cross-package private-submodule imports.

Importing a *peer* scitex package's underscore-prefixed submodule is
fragile (it broke scitex-dsp / scitex-nn when scitex-gen reorganized
`scitex_gen._norm` into `scitex_gen._numeric._norm`). The rule must fire
for cross-package private imports but stay silent for public imports and
same-package private imports.
"""

from scitex_dev.linter._checks._imports import (
    cross_pkg_private_import,
    own_scitex_package,
)
from scitex_dev.linter.checker import lint_source


def _i008_ids(src, filepath):
    return [
        i.rule.id
        for i in lint_source(src, filepath=filepath)
        if i.rule.id == "STX-I008"
    ]


# -- own_scitex_package ----------------------------------------------------


def test_own_package_resolved_from_src_layout():
    # Arrange
    path = "/repo/src/scitex_gen/_numeric/_norm.py"
    # Act
    pkg = own_scitex_package(path)
    # Assert
    assert pkg == "scitex_gen"


def test_own_package_none_for_non_scitex_path():
    # Arrange
    path = "/repo/tests/test_foo.py"
    # Act
    pkg = own_scitex_package(path)
    # Assert
    assert pkg is None


# -- cross_pkg_private_import predicate -------------------------------------


def test_predicate_flags_cross_package_private_module():
    # Arrange
    module = "scitex_gen._numeric._norm"
    # Act
    peer = cross_pkg_private_import(module, own_package="scitex_dsp")
    # Assert
    assert peer == "scitex_gen"


def test_predicate_allows_same_package_private_module():
    # Arrange
    module = "scitex_gen._numeric._norm"
    # Act
    peer = cross_pkg_private_import(module, own_package="scitex_gen")
    # Assert
    assert peer is None


def test_predicate_allows_public_peer_module():
    # Arrange
    module = "scitex_gen"
    # Act
    peer = cross_pkg_private_import(module, own_package="scitex_dsp")
    # Assert
    assert peer is None


# -- end-to-end via lint_source --------------------------------------------


def test_cross_package_private_from_import_is_flagged():
    # Arrange
    src = "from scitex_gen._numeric._norm import to_even\n"
    # Act
    ids = _i008_ids(src, "src/scitex_dsp/_filt.py")
    # Assert
    assert ids == ["STX-I008"]


def test_cross_package_private_bare_import_is_flagged():
    # Arrange
    src = "import scitex_gen._numeric._norm\n"
    # Act
    ids = _i008_ids(src, "src/scitex_dsp/_filt.py")
    # Assert
    assert ids == ["STX-I008"]


def test_cross_package_importing_private_name_is_flagged():
    # Arrange
    src = "from scitex_gen import _numeric\n"
    # Act
    ids = _i008_ids(src, "src/scitex_dsp/_filt.py")
    # Assert
    assert ids == ["STX-I008"]


def test_public_peer_import_is_not_flagged():
    # Arrange
    src = "from scitex_gen import to_even\n"
    # Act
    ids = _i008_ids(src, "src/scitex_dsp/_filt.py")
    # Assert
    assert ids == []


def test_same_package_private_import_is_not_flagged():
    # Arrange
    src = "from scitex_gen._numeric._norm import to_even\n"
    # Act
    ids = _i008_ids(src, "src/scitex_gen/_top.py")
    # Assert
    assert ids == []


def test_non_scitex_private_import_is_not_flagged():
    # Arrange
    src = "from numpy._core import something\n"
    # Act
    ids = _i008_ids(src, "src/scitex_dsp/_filt.py")
    # Assert
    assert ids == []
