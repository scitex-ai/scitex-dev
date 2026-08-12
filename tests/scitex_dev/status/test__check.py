#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :class:`scitex_dev.status.Check`.

The load-bearing property is that an ``unknown`` CANNOT be built without a
reason. That is asserted twice on purpose, because it is enforced twice: the
only constructor that produces one takes the reason positionally, and
``__post_init__`` refuses a blank one so the dataclass constructor cannot get
around it either. A rule enforced in one place is a rule that holds until
someone uses the other door.

The second property is that the wire form is unchanged for the two-valued
cases — four fields, ``ok`` true/false — so migrating a doctor to this type
does not break the readers it already has.

Refusals are captured by :func:`_refusal` and returned rather than asserted
inside a ``raises`` block, keeping each test to ONE assertion.
"""

from __future__ import annotations

from scitex_dev.status import Check, StatusCode, Verdict
from scitex_dev.status._errors import CheckError

_WHY = "compute-04 refused the probe with http 403; its daemon predates the endpoint"
_HOW = "upgrade the remote daemon, then re-run `sac relocate --check`"


def _refusal(**kwargs):
    """Construct a Check and return the refusal it raised, or None."""
    try:
        Check(**kwargs)
    except Exception as exc:  # noqa: BLE001 — the test asserts the exact type
        return exc
    return None


def _parse_refusal(payload):
    """Parse a wire record and return the refusal it raised, or None."""
    try:
        Check.from_dict(payload)
    except Exception as exc:  # noqa: BLE001 — the test asserts the exact type
        return exc
    return None


# -- an unknown must carry WHY ------------------------------------------------


def test_an_unknown_check_keeps_the_reason_it_was_given():
    """The reason is the whole value of the third verdict; it must survive."""
    # Arrange
    check = Check.unknown("may_relocate", _WHY, _HOW)
    # Act
    stored = check.detail
    # Assert
    assert stored == _WHY


def test_a_blank_reason_is_refused_at_construction():
    """The dataclass door is shut too, not just the classmethod one."""
    # Arrange
    kwargs = dict(name="may_relocate", verdict=Verdict.UNKNOWN, detail="", hint=_HOW)
    # Act
    refusal = _refusal(**kwargs)
    # Assert
    assert isinstance(refusal, CheckError)


def test_a_whitespace_only_reason_is_refused_at_construction():
    """A space is not a reason. Whitespace is how a required field gets skipped."""
    # Arrange
    kwargs = dict(name="may_relocate", verdict=Verdict.UNKNOWN, detail="   ", hint=_HOW)
    # Act
    refusal = _refusal(**kwargs)
    # Assert
    assert isinstance(refusal, CheckError)


def test_an_unknown_without_a_way_to_find_out_is_refused():
    """An unknown that names no probe leaves the reader to wait and then guess."""
    # Arrange
    kwargs = dict(name="may_relocate", verdict=Verdict.UNKNOWN, detail=_WHY, hint=None)
    # Act
    refusal = _refusal(**kwargs)
    # Assert
    assert isinstance(refusal, CheckError)


def test_a_not_ok_check_without_a_hint_is_refused():
    """An error that only states what broke is half-written."""
    # Arrange
    kwargs = dict(name="notifyd_alive", verdict=Verdict.NOT_OK, detail="no pidfile")
    # Act
    refusal = _refusal(**kwargs)
    # Assert
    assert isinstance(refusal, CheckError)


def test_an_ok_check_may_omit_the_hint():
    """Nothing to do about a passing check, so nothing is demanded."""
    # Arrange
    check = Check.ok("agent_id", "agent id resolved: scitex-agent-container")
    # Act
    hint = check.hint
    # Assert
    assert hint is None


# -- the three constructors produce three different verdicts ------------------


def test_the_ok_constructor_produces_the_ok_verdict():
    """Asked, answered, good."""
    # Arrange
    check = Check.ok("agent_id", "resolved")
    # Act
    verdict = check.verdict
    # Assert
    assert verdict is Verdict.OK


def test_the_not_ok_constructor_produces_the_not_ok_verdict():
    """Asked, answered, bad."""
    # Arrange
    check = Check.not_ok("notifyd_alive", "no pidfile", "start it: `cards notifyd`")
    # Act
    verdict = check.verdict
    # Assert
    assert verdict is Verdict.NOT_OK


def test_the_unknown_constructor_produces_the_unknown_verdict():
    """Could not find out — which is neither of the other two."""
    # Arrange
    check = Check.unknown("may_relocate", _WHY, _HOW)
    # Act
    verdict = check.verdict
    # Assert
    assert verdict is Verdict.UNKNOWN


def test_a_bare_string_verdict_is_refused():
    """Refused so a comparison against the wrong string fails loudly, not quietly."""
    # Arrange
    kwargs = dict(name="agent_id", verdict="ok", detail="resolved")
    # Act
    refusal = _refusal(**kwargs)
    # Assert
    assert isinstance(refusal, CheckError)


def test_an_anonymous_check_is_refused():
    """An answer that cannot be attributed to a question is not a check."""
    # Arrange
    kwargs = dict(name="", verdict=Verdict.OK, detail="resolved")
    # Act
    refusal = _refusal(**kwargs)
    # Assert
    assert isinstance(refusal, CheckError)


# -- M1 is guidance here, not a validator rule (C5) ---------------------------
#
# Measured against the first real consumer: enforcing `message`'s marker list
# on a check's prose REFUSED scitex-cards' `backend_mode`, whose "therefore"
# is a deduction from two facts the same check supplies. The marker list is
# tuned for short status messages; a check's detail is long by design. The
# structural protection is the verdict, which these tests pin instead.


def test_a_deduction_from_the_checks_own_stated_facts_is_accepted():
    """The real `backend_mode` text. Refusing it would have made the type unadoptable."""
    # Arrange
    detail = (
        "SPLIT BACKENDS — cards are on postgres but the notification inbox is "
        "on yaml. Card writes and notification writes therefore land in "
        "different engines and fail independently — measured 2026-08-01."
    )
    # Act
    check = Check.not_ok("backend_mode", detail, "move the inbox into the card store")
    # Assert
    assert check.detail == detail


def test_reporting_an_observed_cause_with_because_is_allowed():
    """Reporting a cause you saw was never the thing worth refusing."""
    # Arrange
    check = Check.unknown("store_readable", "unreadable because EACCES on the socket", _HOW)
    # Act
    verdict = check.verdict
    # Assert
    assert verdict is Verdict.UNKNOWN


def test_a_checker_that_could_not_establish_a_cause_reports_unknown():
    """The verdict is the structural rule a word list was a poor substitute for."""
    # Arrange
    check = Check.unknown("may_relocate", _WHY, _HOW)
    # Act
    verdict = check.verdict
    # Assert
    assert verdict is Verdict.UNKNOWN


# -- the wire form ------------------------------------------------------------


def test_a_passing_check_serialises_to_exactly_the_four_familiar_fields():
    """Migrating a doctor to this type must not break the readers it already has."""
    # Arrange
    check = Check.ok("agent_id", "resolved")
    # Act
    keys = set(check.to_dict())
    # Assert
    assert keys == {"name", "ok", "detail", "hint"}


def test_an_unknown_check_serialises_its_verdict_as_json_null():
    """The third state rides in `ok`, not in a fifth key nobody would read."""
    # Arrange
    check = Check.unknown("may_relocate", _WHY, _HOW)
    # Act
    wire = check.to_dict()["ok"]
    # Assert
    assert wire is None


def test_a_check_round_trips_through_its_wire_form():
    """A record written by one implementation must parse back to the same check."""
    # Arrange
    check = Check.unknown("may_relocate", _WHY, _HOW)
    # Act
    parsed = Check.from_dict(check.to_dict())
    # Assert
    assert parsed == check


def test_a_separate_verdict_key_is_refused_on_the_wire():
    """Two fields saying the same thing is two fields that can disagree."""
    # Arrange
    payload = {
        "name": "agent_id",
        "ok": True,
        "detail": "resolved",
        "hint": None,
        "verdict": "ok",
    }
    # Act
    refusal = _parse_refusal(payload)
    # Assert
    assert isinstance(refusal, CheckError)


# -- the native code is carried, not paraphrased ------------------------------


def test_an_unknown_carries_the_native_code_that_caused_it():
    """403 stays a real 403 — the specific fact the verdict alone would discard."""
    # Arrange
    cause = StatusCode(
        kind="http",
        code=403,
        message="refused by compute-04; retry after upgrading `sac listen`",
    )
    check = Check.unknown("may_relocate", _WHY, _HOW, cause=cause)
    # Act
    code = check.cause.code
    # Assert
    assert code == 403


def test_the_cause_is_omitted_from_the_wire_form_when_absent():
    """Which is why the common record stays exactly four fields."""
    # Arrange
    check = Check.unknown("may_relocate", _WHY, _HOW)
    # Act
    keys = set(check.to_dict())
    # Assert
    assert "cause" not in keys


# EOF
