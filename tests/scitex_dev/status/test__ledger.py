#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the exchange ledger.

Every exchange yields the SAME shape, so they all go in ONE table and "what
happened to request X" becomes a lookup rather than an investigation.

Two properties are load-bearing:

``final`` is DERIVED from the status code and computed in exactly one place.
It is what makes an unanswered exchange findable — ``final = false`` with an
old ``updated_at`` is the query for work that was accepted and never
concluded. On 2026-08-11 that state was invisible and had to be reconstructed
by hand.

``code`` is stored as JSON so the native value survives. Coercing it to text
would quietly turn the integer 503 into the string "503" and lose the one
guarantee the whole design rests on.
"""

from __future__ import annotations

from scitex_dev.status import StatusCode, ledger_record, ledger_schema, new_exchange_id

_OPENED = "2026-08-11T06:15:08+00:00"


def _record(status, **overrides):
    """Build a ledger row for ``status`` with sensible fixed identity fields."""
    fields = {
        "exchange_id": new_exchange_id(host="scitex-compute-04"),
        "initiator": "laptop/scitex-dev",
        "responder": "scitex-compute-04/scitex-agent-container",
        "operation": "agent.spawn",
        "status": status,
        "opened_at": _OPENED,
    }
    fields.update(overrides)
    return ledger_record(**fields)


def _refusal(**overrides):
    """Build a row and return the refusal it raised, or None."""
    try:
        _record(StatusCode(kind="http", code=200, message="done"), **overrides)
    except Exception as exc:  # noqa: BLE001 — the test asserts the exact type
        return exc
    return None


# -- the schema ---------------------------------------------------------------


def test_the_ledger_schema_is_named_for_status_exchanges():
    """One table, named once, so every package writes to the same place."""
    # Arrange
    schema = ledger_schema()
    # Act
    name = schema.name
    # Assert
    assert name == "status_exchanges"


def test_the_ledger_schema_makes_the_exchange_id_the_identity():
    """The id is the handle every follow-up question is asked with."""
    # Arrange
    schema = ledger_schema()
    # Act
    role = schema.fields["exchange_id"].role
    # Assert
    assert role.value == "identity"


def test_the_ledger_schema_makes_the_initiator_immutable():
    """An exchange's participants cannot change after it opened."""
    # Arrange
    schema = ledger_schema()
    # Act
    merge = schema.fields["initiator"].merge
    # Assert
    assert merge.value == "immutable"


def test_the_ledger_schema_lets_the_message_be_overwritten():
    """A row holds the CURRENT state; the oplog keeps every earlier one."""
    # Arrange
    schema = ledger_schema()
    # Act
    merge = schema.fields["message"].merge
    # Assert
    assert merge.value == "last_writer_wins"


def test_the_ledger_schema_indexes_the_final_flag():
    """ "Accepted and never concluded" has to be a cheap query, not a scan."""
    # Arrange
    schema = ledger_schema()
    # Act
    indexed = schema.fields["final"].indexed
    # Assert
    assert indexed is True


def test_the_ledger_schema_stores_the_code_as_json():
    """int for http/process, str for grpc/dns/errno — both survive verbatim."""
    # Arrange
    schema = ledger_schema()
    # Act
    kind = schema.fields["code"].kind
    # Assert
    assert kind.value == "json"


# -- the record ---------------------------------------------------------------


def test_a_record_derives_final_from_a_completed_status():
    """The flag is computed here, never supplied, so it cannot disagree."""
    # Arrange
    status = StatusCode(kind="http", code=200, message="done")
    # Act
    row = _record(status)
    # Assert
    assert row["final"] is True


def test_a_record_marks_an_accepted_202_as_not_final():
    """The row that must stay findable: accepted, still running."""
    # Arrange
    status = StatusCode(
        kind="http", code=202, message="accepted; poll `sac agents list web-01`"
    )
    # Act
    row = _record(status)
    # Assert
    assert row["final"] is False


def test_a_record_preserves_an_integer_code_verbatim():
    """503 must not become "503" on the way into the store."""
    # Arrange
    status = StatusCode(kind="http", code=503, message="draining; retry in 10s")
    # Act
    row = _record(status)
    # Assert
    assert row["code"] == 503


def test_a_record_preserves_a_string_code_verbatim():
    """NXDOMAIN is the answer; it must arrive as the answer."""
    # Arrange
    status = StatusCode(kind="dns", code="NXDOMAIN", message="no such name")
    # Act
    row = _record(status)
    # Assert
    assert row["code"] == "NXDOMAIN"


def test_a_record_carries_the_status_message_through():
    """The hint is the part a human reads; losing it loses the next action."""
    # Arrange
    status = StatusCode(kind="http", code=503, message="draining; retry in 10s")
    # Act
    row = _record(status)
    # Assert
    assert row["message"] == "draining; retry in 10s"


def test_a_record_defaults_updated_at_when_none_is_given():
    """An undated row cannot answer "accepted and never concluded"."""
    # Arrange
    status = StatusCode(kind="http", code=200, message="done")
    # Act
    row = _record(status)
    # Assert
    assert row["updated_at"] != ""


def test_a_record_keeps_an_explicit_updated_at():
    """A caller replaying history must be able to state the real time."""
    # Arrange
    status = StatusCode(kind="http", code=200, message="done")
    # Act
    row = _record(status, updated_at="2026-08-11T06:20:20+00:00")
    # Assert
    assert row["updated_at"] == "2026-08-11T06:20:20+00:00"


def test_a_malformed_exchange_id_is_refused():
    """A row keyed on a made-up id cannot be found by anyone asking later."""
    # Arrange
    bad = "6f1b2c3d-4e5f-6789-abcd-ef0123456789"
    # Act
    error = _refusal(exchange_id=bad)
    # Assert
    assert isinstance(error, ValueError)


def test_the_malformed_id_refusal_names_the_minting_function():
    """The refusal must hand back the fix, not just the objection."""
    # Arrange
    bad = "not-an-exchange-id"
    # Act
    error = _refusal(exchange_id=bad)
    # Assert
    assert "new_exchange_id" in str(error)


# EOF
