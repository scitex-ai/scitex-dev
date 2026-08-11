#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the two ``message`` rules.

``message`` is a HINT and it is load-bearing: it declares what the sender is
doing, and it hands the receiver the means to verify and to ask. Two rules
make that mechanical.

M1 — NO INFERRED CAUSE. A message states what was MEASURED and what to DO
NEXT; it never names a cause it did not observe. Measured 2026-08-11: a
transport-failure message printed "THEREFORE the fault is specific to
POST /agents" from two control probes that cannot see that route. A reader
acted on it within two minutes and filed a P1 against the wrong component.
The route was fine — the client stopped listening at 30 s while the server
worked the request for 5 min 12 s. Fixed in scitex-agent-container PR #956.

M2 — a code meaning "received, not finished" must say HOW TO ASK. Without a
named probe the reader can only wait and then guess, which is the same
incident from the other side.
"""

from __future__ import annotations

from scitex_dev.status import StatusCode
from scitex_dev.status._errors import InferredCauseError, MissingProbeError


def _refusal(kind, code, message):
    """Construct a StatusCode and return the refusal it raised, or None."""
    try:
        StatusCode(kind=kind, code=code, message=message)
    except Exception as exc:  # noqa: BLE001 — the test asserts the exact type
        return exc
    return None


# -- M1: no inferred cause ----------------------------------------------------


def test_a_message_concluding_therefore_is_refused():
    """The exact word from the 2026-08-11 wrong diagnosis."""
    # Arrange
    message = "no answer in 30s; THEREFORE the route is wedged"
    # Act
    error = _refusal("http", 504, message)
    # Assert
    assert isinstance(error, InferredCauseError)


def test_a_message_asserting_the_fault_is_refused():
    """ "the fault is specific to X" is the claim that cost a P1."""
    # Arrange
    message = "no answer in 30s; the fault is specific to POST /agents"
    # Act
    error = _refusal("http", 504, message)
    # Assert
    assert isinstance(error, InferredCauseError)


def test_a_message_claiming_a_root_cause_is_refused():
    """A hint that names a root cause has stopped being a hint."""
    # Arrange
    message = "spawn failed; root cause is the container runtime"
    # Act
    error = _refusal("http", 500, message)
    # Assert
    assert isinstance(error, InferredCauseError)


def test_a_message_claiming_something_is_proved_is_refused():
    """Two fast control probes prove the daemon is up and nothing more."""
    # Arrange
    message = "control routes answered, which proves that the daemon is fine"
    # Act
    error = _refusal("http", 504, message)
    # Assert
    assert isinstance(error, InferredCauseError)


def test_the_inferred_cause_refusal_names_the_prescribed_shape():
    """The refusal must hand back the fix, not just the objection."""
    # Arrange
    message = "no answer in 30s; therefore the peer is down"
    # Act
    error = _refusal("http", 504, message)
    # Assert
    assert "NOT ESTABLISHED" in str(error)


def test_a_message_reporting_an_observed_cause_is_accepted():
    """Stating a cause you SAW is fine; concluding one you did not is not."""
    # Arrange
    message = "open failed because ENOENT on /etc/scitex/config.yaml; create it"
    # Act
    code = StatusCode(kind="errno", code="ENOENT", message=message)
    # Assert
    assert code.message == message


def test_a_message_in_the_pr956_shape_is_accepted():
    """OBSERVED / RULED OUT / NOT ESTABLISHED / NEXT is the prescribed form."""
    # Arrange
    message = (
        "OBSERVED: no answer in 30s. RULED OUT: a daemon-wide fault, since two "
        "control routes answered. NOT ESTABLISHED: whether the route is wedged "
        "or merely slower than 30s. NEXT, to find out rather than guess: read "
        "`sac agents list web-01`."
    )
    # Act
    code = StatusCode(kind="http", code=504, message=message)
    # Assert
    assert code.message == message


# -- M2: a non-final code must say how to ask ---------------------------------


def test_an_accepted_202_without_a_probe_is_refused():
    """ "Accepted" with no way to ask leaves the reader waiting and guessing."""
    # Arrange
    message = "accepted; still working on it"
    # Act
    error = _refusal("http", 202, message)
    # Assert
    assert isinstance(error, MissingProbeError)


def test_the_missing_probe_refusal_cites_the_measured_incident():
    """The refusal must explain why, or it reads as bureaucracy."""
    # Arrange
    message = "accepted; still working on it"
    # Act
    error = _refusal("http", 202, message)
    # Assert
    assert "5 min 12 s" in str(error)


def test_a_202_with_a_backticked_command_probe_is_accepted():
    """A runnable command is the strongest form of "how to ask"."""
    # Arrange
    message = (
        "accepted as xch_20260811T061508Z_host_a1b2c3; phase=container_creation; "
        "retry in 10s or poll `sac agents list web-01`"
    )
    # Act
    code = StatusCode(kind="http", code=202, message=message)
    # Assert
    assert code.message == message


def test_a_202_with_a_url_probe_is_accepted():
    """A URL is an equally checkable instrument."""
    # Arrange
    message = "accepted; ask https://scitex.ai/agents/web-01 in 10s"
    # Act
    code = StatusCode(kind="http", code=202, message=message)
    # Assert
    assert code.message == message


def test_a_202_with_a_route_path_probe_is_accepted():
    """A route path names a source the reader can consult."""
    # Arrange
    message = "accepted; poll GET /agents/web-01 for the heartbeat"
    # Act
    code = StatusCode(kind="http", code=202, message=message)
    # Assert
    assert code.message == message


def test_a_final_200_needs_no_probe():
    """M2 is about work still running; a completion has nothing to ask about."""
    # Arrange
    message = "done"
    # Act
    code = StatusCode(kind="http", code=200, message=message)
    # Assert
    assert code.message == message


# -- the message must exist at all --------------------------------------------


def test_an_empty_message_is_refused_at_construction():
    """A bare code leaves the receiver with a guess instead of an instrument."""
    # Arrange
    message = "   "
    # Act
    error = _refusal("http", 200, message)
    # Assert
    assert isinstance(error, ValueError)


# EOF
