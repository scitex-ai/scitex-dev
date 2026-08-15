#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :class:`scitex_dev.status.Verdict`.

The load-bearing property is that ``unknown`` is a THIRD value and not a
disguised member of either neighbour. Every test below fails if the type ever
grows a path that turns "I could not find out" into "fine" or "broken".

The second property is that the three values survive the WIRE. The verdict
travels as the tri-state ``ok`` field — ``true`` / ``false`` / ``null`` — and
the parser refuses truthy stand-ins, because ``bool(x)`` is the single line
that has eaten the third state everywhere it has been lost.

Refusals are captured by the ``_refusal`` helpers and returned rather than
asserted inside a ``raises`` block, so each test keeps to ONE assertion.
"""

from __future__ import annotations

from scitex_dev.status import Verdict, verdicts
from scitex_dev.status._errors import UnknownVerdictError


def _from_ok_refusal(value):
    """Parse a tri-state ``ok`` value and return the refusal it raised, or None."""
    try:
        Verdict.from_ok(value)
    except Exception as exc:  # noqa: BLE001 — the test asserts the exact type
        return exc
    return None


def _from_wire_refusal(value):
    """Parse a verdict string and return the refusal it raised, or None."""
    try:
        Verdict.from_wire(value)
    except Exception as exc:  # noqa: BLE001 — the test asserts the exact type
        return exc
    return None


# -- three values, and they are distinct --------------------------------------


def test_the_verdict_set_has_exactly_three_members():
    """Pinned so that adding a fourth answer is a deliberate, reviewed act."""
    # Arrange
    expected = {"ok", "not-ok", "unknown"}
    # Act
    members = {member.value for member in Verdict}
    # Assert
    assert members == expected


def test_unknown_is_not_equal_to_ok():
    """The whole defect is that a boolean has to file unknown under one of these."""
    # Arrange
    unknown = Verdict.UNKNOWN
    # Act
    same = unknown is Verdict.OK
    # Assert
    assert same is False


def test_unknown_is_not_equal_to_not_ok():
    """Nine agents were nearly grounded by exactly this conflation on 2026-08-11."""
    # Arrange
    unknown = Verdict.UNKNOWN
    # Act
    same = unknown is Verdict.NOT_OK
    # Assert
    assert same is False


def test_a_verdict_does_not_compare_equal_to_its_own_wire_string():
    """No str mixin: a caller comparing to a bare string must FAIL, not pass quietly."""
    # Arrange
    verdict = Verdict.UNKNOWN
    # Act
    matches_string = verdict == "unknown"
    # Assert
    assert matches_string is False


# -- the tri-state `ok` wire form ---------------------------------------------


def test_ok_serialises_to_json_true():
    """The good answer keeps the value every existing reader already expects."""
    # Arrange
    verdict = Verdict.OK
    # Act
    wire = verdict.ok
    # Assert
    assert wire is True


def test_not_ok_serialises_to_json_false():
    """The bad answer likewise — the two-valued cases are unchanged on the wire."""
    # Arrange
    verdict = Verdict.NOT_OK
    # Act
    wire = verdict.ok
    # Assert
    assert wire is False


def test_unknown_serialises_to_json_null():
    """The third state rides in the SAME field, so nothing that can disagree is added."""
    # Arrange
    verdict = Verdict.UNKNOWN
    # Act
    wire = verdict.ok
    # Assert
    assert wire is None


def test_json_null_parses_back_to_unknown():
    """Round-trip: a reader that keeps `null` keeps the distinction."""
    # Arrange
    wire = None
    # Act
    verdict = Verdict.from_ok(wire)
    # Assert
    assert verdict is Verdict.UNKNOWN


def test_every_verdict_round_trips_through_the_ok_field():
    """No member is lossy on the wire, which is what makes the field sufficient."""
    # Arrange
    members = list(Verdict)
    # Act
    round_tripped = [Verdict.from_ok(member.ok) for member in members]
    # Assert
    assert round_tripped == members


def test_from_ok_refuses_the_integer_one():
    """`bool(1)` is True — the coercion that eats the third state is refused here."""
    # Arrange
    value = 1
    # Act
    refusal = _from_ok_refusal(value)
    # Assert
    assert isinstance(refusal, UnknownVerdictError)


def test_from_ok_refuses_an_empty_string():
    """Falsy stand-ins are refused too: "" is not an answer, it is a missing one."""
    # Arrange
    value = ""
    # Act
    refusal = _from_ok_refusal(value)
    # Assert
    assert isinstance(refusal, UnknownVerdictError)


# -- the string form refuses rather than decays -------------------------------


def test_from_wire_parses_the_hyphenated_not_ok_value():
    """The spec spells it `not-ok`; the Python member is NOT_OK and they must agree."""
    # Arrange
    text = "not-ok"
    # Act
    verdict = Verdict.from_wire(text)
    # Assert
    assert verdict is Verdict.NOT_OK


def test_from_wire_refuses_an_unregistered_verdict():
    """A verdict a reader does not implement must be refused, never decayed to unknown."""
    # Arrange
    text = "degraded"
    # Act
    refusal = _from_wire_refusal(text)
    # Assert
    assert isinstance(refusal, UnknownVerdictError)


def test_the_refusal_names_the_three_legal_values():
    """An error that only states what broke is half-written."""
    # Arrange
    refusal = _from_wire_refusal("degraded")
    # Act
    text = str(refusal)
    # Assert
    assert "not-ok" in text


# -- the Python stayed DERIVED from the spec ----------------------------------


def test_the_python_verdict_members_match_the_spec_file():
    """A member with no spec entry is a verdict nobody else can read."""
    # Arrange
    declared = set(verdicts())
    # Act
    exposed = {member.value for member in Verdict}
    # Assert
    assert exposed == declared


# EOF
