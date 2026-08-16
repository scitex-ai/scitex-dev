#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_cli/ecosystem/_cmds/test__install_cross_package_gate.py

"""Tests for the PS-140 cross-package gate generator.

The mirror file for `_install_cross_package_gate.py`, which had none — the
generator has been emitting deployed test files since 2026-07-29 with no
test of its own output.

Two of these pin properties that a reader might "clean up" and thereby
break silently:

* the emitted list must stay a plain `Assign` of a `List` of string
  `Constant`s, because PS-140's `_read_declared_imports` parses it back
  out with AST. An f-string or comprehension would render the auditor
  blind while looking tidier.
* the emitted import must stay a HARD `importlib.import_module`, never
  `pytest.importorskip`. A cross-package gate exists to go RED when a
  peer renames a module; a skip converts exactly that event into green.
"""

from __future__ import annotations

import ast

from scitex_dev._cli.ecosystem._cmds._install_cross_package_gate import (
    render_cross_package_gate,
)

DIST = "scitex-demo"
IMPORTS = ["scitex_config", "scitex_io"]


def _render() -> str:
    return render_cross_package_gate(DIST, IMPORTS)


def _declared_imports(source: str) -> list[str]:
    """Read the list back the way PS-140's auditor does — via AST."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "CROSS_PACKAGE_IMPORTS"
            for t in node.targets
        ):
            return [
                el.value
                for el in node.value.elts
                if isinstance(el, ast.Constant) and isinstance(el.value, str)
            ]
    return []


def test_rendered_gate_is_valid_python():
    # Arrange
    source = _render()
    # Act
    tree = ast.parse(source)
    # Assert
    assert tree is not None


def test_rendered_gate_carries_a_version_stamp():
    """A gate nobody can date is a claim about an unknown past."""
    # Arrange
    source = _render()
    # Act
    stamped = [line for line in source.splitlines() if "generated-by:" in line]
    # Assert
    assert stamped


def test_the_stamp_names_scitex_dev():
    # Arrange
    source = _render()
    # Act
    stamped = [line for line in source.splitlines() if "generated-by:" in line]
    # Assert
    assert "scitex-dev" in stamped[0]


def test_declared_imports_survive_an_ast_round_trip():
    """PS-140's auditor reads this list back with AST, not a regex."""
    # Arrange
    source = _render()
    # Act
    parsed = _declared_imports(source)
    # Assert
    assert parsed == sorted(IMPORTS)


def test_gate_uses_a_hard_import_not_importorskip():
    """A skip would convert a renamed peer module into a green run."""
    # Arrange
    source = _render()
    # Act
    uses_hard_import = "importlib.import_module" in source
    # Assert
    assert uses_hard_import


def test_gate_never_emits_importorskip():
    # Arrange
    source = _render()
    # Act
    skips = "importorskip" in source
    # Assert
    assert not skips


def test_gate_names_the_command_that_regenerates_it():
    """The docstring must name a command that actually exists.

    Measured 2026-08-16: 17 gates across the fleet credited
    `scitex-dev ecosystem write-integration-tests`, which has never been a
    verb -- the real writer was a one-shot script in /tmp, since deleted.
    A file whose stated regeneration path does not exist cannot be
    refreshed, and nothing says so.
    """
    # Arrange
    source = _render()
    # Act
    names_real_verb = "install-cross-package-gate" in source
    # Assert
    assert names_real_verb


# EOF
