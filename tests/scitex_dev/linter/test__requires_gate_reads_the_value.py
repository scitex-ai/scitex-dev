#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The ``requires=`` gate must read availability, not dict membership.

Reported by scitex-db, 2026-08-09: STX-S001 ("Missing @stx.session on
main()") fires in a venv where ``import scitex`` raises, so the only way
to a green run is to ignore the rule. Reproduced here before fixing.

THE BUG WAS ONE OPERATOR. ``_packages.detect()`` returns a DICT::

    {"scitex": False, "figrecipe": False}

and ``SciTeXChecker._add`` tested::

    if rule.requires and rule.requires not in self._available:   # WRONG

``in`` on a dict tests KEYS. ``"scitex"`` is always a key, present whether
or not the package imports, so the branch was never taken and the computed
boolean was discarded. A gate that cannot fail — the constitution's §2 case
— and it failed in BOTH directions at once:

* rules whose precondition was absent still fired (a rule demanding an
  import the environment cannot satisfy is unsatisfiable, not strict), and
* ``record_rule_skip`` never ran, so the "NOT ALL RULES RAN" summary
  reported only the io/path group and claimed a completeness it did not
  have.

Measured in this container (``/opt/venv-sac``, where ``import scitex``
raises ModuleNotFoundError): a script with a bare ``main()`` reported
"1 error, 1 warning" — STX-S001 and STX-S005, both ``requires="scitex"``.

NOTE ON METHOD. These tests drive the real checker over real source with
real Rule objects. Nothing is patched: ``requires`` values that name a
genuinely-absent package are gated, and a rule with no ``requires`` is the
positive control proving the checker still emits. Without that control a
gate that skipped EVERYTHING would pass this file.
"""

from __future__ import annotations

import pytest

from scitex_dev.linter import _packages
from scitex_dev.linter._rules._base import Rule
from scitex_dev.linter.checker import SciTeXChecker

_SOURCE = "x = 1\n"


@pytest.fixture
def checker() -> SciTeXChecker:
    """A real checker over real source."""
    _packages.reset()
    return SciTeXChecker(_SOURCE.splitlines(), filepath="probe.py")


def _rule(requires: "str | None") -> Rule:
    """A minimal real Rule carrying the requires value under test."""
    return Rule(
        id="STX-TEST001",
        severity="error",
        category="structure",
        message="probe",
        suggestion="probe",
        requires=requires,
    )


def test_a_rule_requiring_an_absent_package_does_not_fire(checker):
    """scitex is genuinely not importable here, so S-rules must stay quiet."""
    # Arrange
    rule = _rule("scitex")

    # Act
    checker._add(rule, 1, 0, "")

    # Assert
    assert checker.issues == []


def test_a_rule_requiring_an_unknown_package_does_not_fire(checker):
    """An unrecognised requirement is absent, not implicitly satisfied."""
    # Arrange
    rule = _rule("a-package-that-does-not-exist")

    # Act
    checker._add(rule, 1, 0, "")

    # Assert
    assert checker.issues == []


def test_a_rule_with_no_requires_still_fires(checker):
    """POSITIVE CONTROL: the gate must not silence everything."""
    # Arrange
    rule = _rule(None)

    # Act
    checker._add(rule, 1, 0, "")

    # Assert
    assert len(checker.issues) == 1


def test_availability_is_reported_as_a_boolean_value(checker):
    """The dict's VALUE is what the gate must consult."""
    # Arrange
    _packages.reset()

    # Act
    available = _packages.detect()

    # Assert
    assert available["scitex"] is False


def test_the_package_name_is_present_as_a_key_even_when_absent(checker):
    """This is WHY membership was the wrong test — pin it so it cannot regress.

    If someone later makes `detect()` omit absent packages, membership would
    start working by accident and this test says why that is not the fix.
    """
    # Arrange
    _packages.reset()

    # Act
    available = _packages.detect()

    # Assert
    assert "scitex" in available


def test_a_gated_rule_records_the_skip_so_the_verdict_is_qualified(checker):
    """A skipped rule must be REPORTED, or the run claims false completeness."""
    # Arrange
    from scitex_dev.linter import _health

    _health.reset()
    rule = _rule("scitex")

    # Act
    checker._add(rule, 1, 0, "")

    # Assert
    assert any(
        r["kind"] == "requires_gate" and r["requires"] == "scitex"
        for r in _health.skipped_categories()
    )

# EOF
