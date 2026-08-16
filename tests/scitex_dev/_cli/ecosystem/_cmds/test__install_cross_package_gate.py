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

from scitex_dev._cli.ecosystem._cmds._gate_sentinel import (
    BEGIN_SENTINEL,
    END_SENTINEL,
    split_at_sentinel,
)
from scitex_dev._cli.ecosystem._cmds._install_cross_package_gate import (
    DEFAULT_GATE_TAIL,
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


def test_rendered_gate_opens_the_generated_region():
    """Without a BEGIN marker there is no delimited generated region."""
    # Arrange
    source = _render()
    # Act
    opens = BEGIN_SENTINEL in source
    # Assert
    assert opens


def test_rendered_gate_closes_the_generated_region():
    """The closing marker is where user territory starts.

    The renderer emitted NEITHER sentinel until 2026-08-16 while the
    deployed population carried both and invited hand-written cases below
    the second one. Regenerating therefore did not merely fail to preserve
    a tail -- it deleted the only defined home for one.
    """
    # Arrange
    source = _render()
    # Act
    closes = END_SENTINEL in source
    # Assert
    assert closes


def test_a_supplied_tail_is_preserved_byte_identically():
    """The whole point: regeneration hands back the bytes it found."""
    # Arrange
    tail = END_SENTINEL + "\n\n\ndef test_hand_written():\n    assert True\n"
    # Act
    source = render_cross_package_gate(DIST, IMPORTS, tail=tail)
    # Assert
    assert source.endswith(tail)


def test_preserved_tail_keeps_a_deliberately_strengthened_assertion():
    """scitex-io strengthened its assertion in place; do not revert it.

    Its gate asserts `mod.__name__ == module_name` rather than the
    template's `mod is not None`. A regenerator that owned the region
    below the sentinel would silently undo that -- a downgrade reported
    as a successful refresh.
    """
    # Arrange
    strengthened = (
        END_SENTINEL + "\n\n\ndef test_x(m):\n    assert m.__name__ == m\n"
    )
    # Act
    source = render_cross_package_gate(DIST, IMPORTS, tail=strengthened)
    # Assert
    assert "m.__name__ == m" in source


def test_regenerated_list_is_still_ast_readable_with_a_tail():
    """Preserving a tail must not break what the auditor parses."""
    # Arrange
    tail = END_SENTINEL + "\n\n\ndef test_hand_written():\n    assert True\n"
    # Act
    source = render_cross_package_gate(DIST, IMPORTS, tail=tail)
    # Assert
    assert _declared_imports(source) == sorted(IMPORTS)


def test_absent_tail_yields_the_default_body():
    """None means 'no existing file', not 'an empty user region'."""
    # Arrange
    source = render_cross_package_gate(DIST, IMPORTS, tail=None)
    # Act
    has_default_test = "def test_cross_package_import_resolves" in source
    # Assert
    assert has_default_test


def test_the_default_tail_hard_imports_rather_than_skipping():
    """A gate that skips on the FULL path cannot fail for its own purpose.

    Measured 2026-08-16 by dry-running the regenerator before a pilot sweep:
    ALL 19 deployed gates — this repo's included — call
    `pytest.importorskip(module_name)` on the full dotted path. That skips on
    any ImportError, and a renamed submodule raises ModuleNotFoundError, an
    ImportError subclass. So the rename SKIPS and control never reaches the
    hard import on the next line. The deployed docstring claims that case
    "FAILS loudly"; it cannot.

    Root-level skip stays legitimate — a peer genuinely absent from a leaf
    repo's CI should not fail that repo. Absent-peer and broken-path are
    different states, and the deployed shape collapses them.

    This test pins only what THIS renderer emits. Fixing the 19 deployed
    tails is tracked separately: regeneration preserves them byte-identically,
    so a sweep does not touch the broken assertion.
    """
    # Arrange
    tail = DEFAULT_GATE_TAIL
    # Act
    skips_on_missing = "importorskip" in tail
    # Assert
    assert not skips_on_missing


def test_split_of_a_rendered_gate_round_trips():
    """What this renderer writes, the splitter must be able to read back.

    Generator and preserver agreeing is the property that makes repeated
    regeneration safe; if they disagree on where the boundary is, the
    second run eats what the first one wrote.
    """
    # Arrange
    tail = END_SENTINEL + "\n\n\ndef test_hand_written():\n    assert True\n"
    rendered = render_cross_package_gate(DIST, IMPORTS, tail=tail)
    # Act
    split = split_at_sentinel(rendered)
    # Assert
    assert split.tail == tail


# EOF
