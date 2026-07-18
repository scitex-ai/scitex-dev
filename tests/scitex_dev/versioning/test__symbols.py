#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Symbol probes against REAL modules (no mocks).

The True/False/None distinction is the whole point: absent symbol / absent
module => False (positive evidence the fix is not here); a module whose OWN
dependency is broken => None (UNKNOWN — tells us nothing about our symbol, and
a False here would be a dangerous false RED someone acts on).

The UNKNOWN case is driven by writing a real module to ``tmp_path`` that
imports a genuinely-missing dependency, then importing it for real.
"""

from __future__ import annotations

import sys

from scitex_dev.versioning._symbols import SymbolExpectation, probe

# A module + symbol that genuinely exist in this checkout.
REAL_MODULE = "scitex_dev.versioning._symbols"


def test_present_symbol_probes_true():
    # Arrange
    exp = SymbolExpectation(module=REAL_MODULE, symbol="probe", since="0.0.0", why="the probe fn")
    # Act
    result = probe(exp)
    # Assert
    assert result is True


def test_absent_symbol_probes_false():
    # Arrange
    exp = SymbolExpectation(module=REAL_MODULE, symbol="never_written", since="9.9.9", why="nope")
    # Act
    result = probe(exp)
    # Assert
    assert result is False


def test_absent_module_probes_false():
    # Arrange
    exp = SymbolExpectation(
        module="scitex_dev.versioning._never_shipped", symbol="x", since="9.9.9", why="nope"
    )
    # Act
    result = probe(exp)
    # Assert
    assert result is False


def test_broken_dependency_probes_none(tmp_path):
    # Arrange — a real module that really fails to import for a reason that
    # has nothing to do with the symbol we ask about.
    broken = tmp_path / "vers_broken_probe.py"
    broken.write_text("import a_package_that_is_not_installed_anywhere\n")
    sys.path.insert(0, str(tmp_path))
    exp = SymbolExpectation(
        module="vers_broken_probe", symbol="anything", since="9.9.9", why="dep missing"
    )
    # Act
    try:
        result = probe(exp)
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("vers_broken_probe", None)
    # Assert
    assert result is None


# EOF
