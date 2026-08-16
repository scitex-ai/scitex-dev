#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_cli/ecosystem/_cmds/test__gate_sentinel.py

"""Tests for :mod:`scitex_dev._cli._cmds._gate_sentinel`.

The load-bearing test is `test_tail_is_preserved_byte_identically`. The
property is not "the tests below the sentinel survive" but "EVERYTHING
below it survives, unchanged" — scitex-dev's own gate carries a documented
prose block down there, and a tests-aware preserver would drop exactly that
while passing a looser test.

The fixtures are the real shapes scitex-hpc measured across 20 checkouts on
2026-08-16, not invented ones.
"""

from __future__ import annotations

from scitex_dev._cli.ecosystem._cmds._gate_sentinel import (
    END_SENTINEL,
    SplitGate,
    split_at_sentinel,
)

# The scitex-dev shape: a test AND prose. The prose is the reason the
# contract is "everything after", not "the tests after".
TAIL_WITH_PROSE = f'''{END_SENTINEL}


@pytest.mark.parametrize("module_name", CROSS_PACKAGE_IMPORTS)
def test_cross_package_import_returns_non_none_module(module_name):
    # Arrange
    # Act
    mod = pytest.importorskip(module_name)
    # Assert
    assert mod is not None


#: Roots reached through a compat-ALIAS shim, where ``__name__`` reports the
#: CANONICAL module rather than the name that was requested — by design.
ALIAS_ROOTS = ("scitex_io",)
'''

# The scitex-io shape: no added test, but the GENERATED one deliberately
# strengthened. A "regenerate, the block is authoritative" approach reverts
# this silently, which is why it counts as preservable content.
TAIL_STRENGTHENED = f'''{END_SENTINEL}


@pytest.mark.parametrize("module_name", CROSS_PACKAGE_IMPORTS)
def test_cross_package_import_resolves(module_name):
    mod = pytest.importorskip(module_name)
    assert mod.__name__ == module_name
'''

HEAD = '"""Cross-package import gate."""\n\nCROSS_PACKAGE_IMPORTS = [\n    "scitex_io",\n]\n\n'


def test_absent_file_reports_readable():
    # Arrange
    existing = None
    # Act
    result = split_at_sentinel(existing)
    # Assert
    assert result.readable


def test_absent_file_has_no_sentinel():
    # Arrange
    existing = None
    # Act
    result = split_at_sentinel(existing)
    # Assert
    assert not result.has_sentinel


def test_absent_file_yields_an_empty_tail():
    # Arrange
    existing = None
    # Act
    result = split_at_sentinel(existing)
    # Assert
    assert result.tail == ""


def test_file_without_a_sentinel_reports_none_found():
    """The 3 hand-authored PS-140 gates have no AUTO-GENERATED block."""
    # Arrange
    existing = '"""Cross-package integration gate (PS-140)."""\n'
    # Act
    result = split_at_sentinel(existing)
    # Assert
    assert not result.has_sentinel


def test_file_without_a_sentinel_yields_no_tail():
    # Arrange
    existing = '"""Cross-package integration gate (PS-140)."""\n'
    # Act
    result = split_at_sentinel(existing)
    # Assert
    assert result.tail == ""


def test_sentinel_is_detected_when_present():
    # Arrange
    existing = HEAD + TAIL_WITH_PROSE
    # Act
    result = split_at_sentinel(existing)
    # Assert
    assert result.has_sentinel


def test_tail_is_preserved_byte_identically():
    """THE contract. Not 'the tests survive' -- EVERYTHING survives."""
    # Arrange
    existing = HEAD + TAIL_WITH_PROSE
    # Act
    result = split_at_sentinel(existing)
    # Assert
    assert result.tail == TAIL_WITH_PROSE


def test_preserved_tail_keeps_non_test_prose():
    """scitex-dev's tail is partly documentation, not code."""
    # Arrange
    existing = HEAD + TAIL_WITH_PROSE
    # Act
    result = split_at_sentinel(existing)
    # Assert
    assert "compat-ALIAS shim" in result.tail


def test_a_strengthened_generated_test_is_preserved():
    """scitex-io replaced `is not None` with an identity assertion."""
    # Arrange
    existing = HEAD + TAIL_STRENGTHENED
    # Act
    result = split_at_sentinel(existing)
    # Assert
    assert "mod.__name__ == module_name" in result.tail


def test_the_head_is_not_carried_into_the_tail():
    """Regeneration replaces the head; leaking it would duplicate the list."""
    # Arrange
    existing = HEAD + TAIL_WITH_PROSE
    # Act
    result = split_at_sentinel(existing)
    # Assert
    assert "CROSS_PACKAGE_IMPORTS = [" not in result.tail


def test_tail_starts_at_the_closing_sentinel():
    """The caller concatenates head + tail, so the marker must survive."""
    # Arrange
    existing = HEAD + TAIL_WITH_PROSE
    # Act
    result = split_at_sentinel(existing)
    # Assert
    assert result.tail.startswith(END_SENTINEL)


def test_unreadable_result_cannot_carry_invented_content():
    """A guard against constructing 'nothing was read, but here is a tail'."""
    # Arrange
    readable = False
    # Act / Assert
    # Assert
    try:
        SplitGate(readable=readable, has_sentinel=False, tail="something")
        raised = False
    except ValueError:
        raised = True
    assert raised


# EOF
