#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :class:`scitex_dev.status.StatusCode`.

The load-bearing property is that the NATIVE code survives untouched. A
canonical-vocabulary design would map ``process 137`` onto some
"resource exhausted" word and destroy the fact that it was SIGKILL — which is
usually the only thing worth knowing. These tests pin that it does not happen.

The second property is that a malformed value cannot be CONSTRUCTED at all.
Every refusal below happens in ``__post_init__``, not three layers downstream
where the context that would explain it is gone.

Refusals are captured by :func:`_refusal` and returned rather than asserted
inside a ``raises`` block. That keeps each test to ONE assertion while still
letting a separate test inspect the message — the alternative is a ``raises``
block plus asserts, which is the two-assertion shape TQ007 exists to prevent.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

from scitex_dev.status import StatusCode
from scitex_dev.status._errors import UnknownCodeError, UnknownKindError

_PROBE_MSG = "accepted; poll `sac agents list web-01` to check"


def _refusal(kind, code, message):
    """Construct a StatusCode and return the refusal it raised, or None."""
    try:
        StatusCode(kind=kind, code=code, message=message)
    except Exception as exc:  # noqa: BLE001 — the test asserts the exact type
        return exc
    return None


def _parse_refusal(payload):
    """Parse a wire payload and return the refusal it raised, or None."""
    try:
        StatusCode.from_dict(payload)
    except Exception as exc:  # noqa: BLE001 — the test asserts the exact type
        return exc
    return None


# -- the code is preserved verbatim -------------------------------------------


def test_http_status_code_preserves_the_native_code_verbatim():
    """503 stays the integer 503 — no translation, no canonical word."""
    # Arrange
    code = StatusCode(kind="http", code=503, message="draining; retry in 10s")
    # Act
    stored = code.code
    # Assert
    assert stored == 503


def test_process_status_code_preserves_sigkill_exit_137():
    """137 is 128+9 = SIGKILL. Folding it into a canonical word loses that."""
    # Arrange
    code = StatusCode(kind="process", code=137, message="killed by SIGKILL")
    # Act
    stored = code.code
    # Assert
    assert stored == 137


def test_dns_status_code_preserves_the_nxdomain_rcode():
    """NXDOMAIN and SERVFAIL are different problems with different fixes."""
    # Arrange
    code = StatusCode(kind="dns", code="NXDOMAIN", message="name does not exist")
    # Act
    stored = code.code
    # Assert
    assert stored == "NXDOMAIN"


def test_status_code_is_frozen_against_mutation():
    """A status is a claim someone made; it must not be edited afterwards."""
    # Arrange
    code = StatusCode(kind="http", code=200, message="done")
    # Act
    try:
        code.code = 500
        error = None
    except FrozenInstanceError as exc:
        error = exc
    # Assert
    assert isinstance(error, FrozenInstanceError)


# -- kind validation ----------------------------------------------------------


def test_an_unregistered_kind_is_refused_at_construction():
    """An unknown kind is refused, never defaulted — the tag must be trusted."""
    # Arrange
    kind = "smtp"
    # Act
    error = _refusal(kind, 550, "rejected")
    # Assert
    assert isinstance(error, UnknownKindError)


def test_the_unknown_kind_refusal_lists_the_registered_kinds():
    """An error that only states what broke is half-written."""
    # Arrange
    kind = "smtp"
    # Act
    error = _refusal(kind, 550, "rejected")
    # Assert
    assert "http" in str(error)


# -- code validation, per kind ------------------------------------------------


def test_an_http_code_outside_the_enumeration_is_refused():
    """999 passes a 100-599 range test and is still a typo wearing a uniform."""
    # Arrange
    code = 999
    # Act
    error = _refusal("http", code, "what")
    # Assert
    assert isinstance(error, UnknownCodeError)


def test_an_http_code_below_the_valid_range_is_refused():
    """A range check still has to exist underneath the enumeration."""
    # Arrange
    code = 99
    # Act
    error = _refusal("http", code, "what")
    # Assert
    assert isinstance(error, UnknownCodeError)


def test_an_http_code_given_as_a_string_is_refused():
    """kind=http declares an INTEGER code; "503" is a different type."""
    # Arrange
    code = "503"
    # Act
    error = _refusal("http", code, "draining")
    # Assert
    assert isinstance(error, UnknownCodeError)


def test_a_process_code_above_255_is_refused():
    """POSIX exit status is a byte; 256 never comes back from waitpid."""
    # Arrange
    code = 256
    # Act
    error = _refusal("process", code, "impossible")
    # Assert
    assert isinstance(error, UnknownCodeError)


def test_a_grpc_name_outside_the_canonical_seventeen_is_refused():
    """gRPC has exactly 17 status names; RATE_LIMITED is not one of them."""
    # Arrange
    code = "RATE_LIMITED"
    # Act
    error = _refusal("grpc", code, "slow down")
    # Assert
    assert isinstance(error, UnknownCodeError)


def test_a_dns_rcode_outside_the_registry_is_refused():
    """RFC 1035 / 6895 name the RCODEs; NOTFOUND is not among them."""
    # Arrange
    code = "NOTFOUND"
    # Act
    error = _refusal("dns", code, "no such name")
    # Assert
    assert isinstance(error, UnknownCodeError)


def test_an_errno_number_is_refused_in_favour_of_the_name():
    """errno NUMBERS are platform-specific and change meaning in transit."""
    # Arrange
    code = 2
    # Act
    error = _refusal("errno", code, "no such file")
    # Assert
    assert isinstance(error, UnknownCodeError)


def test_the_errno_number_refusal_explains_the_portability_reason():
    """The fix ("send the name") must be in the message, not inferred."""
    # Arrange
    code = 2
    # Act
    error = _refusal("errno", code, "no such file")
    # Assert
    assert "platform-specific" in str(error)


def test_an_errno_name_unknown_to_the_platform_is_refused():
    """The valid set comes from the platform's own errno table, not a list."""
    # Arrange
    code = "ENOTAREALERRNO"
    # Act
    error = _refusal("errno", code, "invented")
    # Assert
    assert isinstance(error, UnknownCodeError)


def test_a_real_errno_name_is_accepted():
    """ECONNREFUSED is the honest word for "nothing listening"."""
    # Arrange
    code = StatusCode(kind="errno", code="ECONNREFUSED", message="nothing listening")
    # Act
    stored = code.code
    # Assert
    assert stored == "ECONNREFUSED"


def test_a_scitex_code_outside_the_closed_enumeration_is_refused():
    """The scitex list is closed; a long one means the rejected design regrew."""
    # Arrange
    code = "UNAVAILABLE"
    # Act
    error = _refusal("scitex", code, "down")
    # Assert
    assert isinstance(error, UnknownCodeError)


def test_the_registered_scitex_not_resolvable_code_is_accepted():
    """ "Installed but not on this PATH" has no native code anywhere."""
    # Arrange
    code = StatusCode(
        kind="scitex",
        code="NOT_RESOLVABLE",
        message="sac is installed at ~/.env-sac/bin/sac; add it to PATH",
    )
    # Act
    stored = code.code
    # Assert
    assert stored == "NOT_RESOLVABLE"


# -- the wire form: three keys, nothing derived -------------------------------


def test_to_dict_emits_exactly_three_keys():
    """The type is three fields and the wire form is those three fields."""
    # Arrange
    code = StatusCode(kind="http", code=200, message="done")
    # Act
    payload = code.to_dict()
    # Assert
    assert set(payload) == {"kind", "code", "message"}


def test_to_dict_never_emits_the_derived_ok_field():
    """Two fields that can disagree eventually will. `ok` is derived, not sent."""
    # Arrange
    code = StatusCode(kind="http", code=200, message="done")
    # Act
    payload = code.to_dict()
    # Assert
    assert "ok" not in payload


def test_from_dict_refuses_a_payload_carrying_ok():
    """The key someone will helpfully add back is refused on arrival."""
    # Arrange
    payload = {"kind": "http", "code": 200, "message": "done", "ok": True}
    # Act
    error = _parse_refusal(payload)
    # Assert
    assert isinstance(error, ValueError)


def test_from_dict_refuses_a_payload_carrying_retryable():
    """Retryability is readable from the code; `message` says the useful part."""
    # Arrange
    payload = {"kind": "http", "code": 503, "message": "retry", "retryable": True}
    # Act
    error = _parse_refusal(payload)
    # Assert
    assert isinstance(error, ValueError)


def test_from_dict_round_trips_a_valid_payload():
    """The wire form parses back to an equal value."""
    # Arrange
    code = StatusCode(kind="grpc", code="UNAVAILABLE", message="worker offline")
    # Act
    restored = StatusCode.from_dict(code.to_dict())
    # Assert
    assert restored == code


# -- `ok` is derived ----------------------------------------------------------


def test_ok_is_true_for_a_2xx_http_code():
    """Within HTTP's own vocabulary, 2xx reports success."""
    # Arrange
    code = StatusCode(kind="http", code=200, message="done")
    # Act
    verdict = code.ok
    # Assert
    assert verdict is True


def test_ok_is_false_for_a_5xx_http_code():
    """503 does not report success in anyone's reading."""
    # Arrange
    code = StatusCode(kind="http", code=503, message="draining; retry in 10s")
    # Act
    verdict = code.ok
    # Assert
    assert verdict is False


def test_ok_is_true_for_process_exit_zero():
    """A process's success word is 0, not 200."""
    # Arrange
    code = StatusCode(kind="process", code=0, message="completed")
    # Act
    verdict = code.ok
    # Assert
    assert verdict is True


def test_ok_is_false_for_a_nonzero_process_exit():
    """Exit 1 is a generic failure and is reserved from SciTeX meanings."""
    # Arrange
    code = StatusCode(kind="process", code=1, message="failed; see stderr")
    # Act
    verdict = code.ok
    # Assert
    assert verdict is False


def test_ok_is_true_for_the_grpc_ok_name():
    """gRPC's success word is the name OK, not a number."""
    # Arrange
    code = StatusCode(kind="grpc", code="OK", message="completed")
    # Act
    verdict = code.ok
    # Assert
    assert verdict is True


def test_ok_is_false_for_any_errno_name():
    """errno names exist only to report a problem."""
    # Arrange
    code = StatusCode(kind="errno", code="EACCES", message="permission denied")
    # Act
    verdict = code.ok
    # Assert
    assert verdict is False


# -- `ok` and `final` are different questions ---------------------------------


def test_http_202_reports_ok_because_it_really_was_accepted():
    """202 is a genuine success of the ACK — the request did land."""
    # Arrange
    code = StatusCode(kind="http", code=202, message=_PROBE_MSG)
    # Act
    verdict = code.ok
    # Assert
    assert verdict is True


def test_http_202_is_not_final_because_the_work_continues():
    """Reading "accepted" as "done" and "not done" as "failed" are twin bugs."""
    # Arrange
    code = StatusCode(kind="http", code=202, message=_PROBE_MSG)
    # Act
    verdict = code.final
    # Assert
    assert verdict is False


def test_http_200_is_final_because_the_work_completed():
    """A completion is a separate, later fact from the ack."""
    # Arrange
    code = StatusCode(kind="http", code=200, message="done")
    # Act
    verdict = code.final
    # Assert
    assert verdict is True


def test_http_504_is_final_as_a_statement_about_the_caller():
    """504 says "I stopped waiting" — the caller's own account is complete."""
    # Arrange
    code = StatusCode(
        kind="http",
        code=504,
        message="stopped waiting after 30s; ask `sac agents list web-01`",
    )
    # Act
    verdict = code.final
    # Assert
    assert verdict is True


def test_a_process_exit_is_always_final():
    """A process that exited is done, whatever it exited with."""
    # Arrange
    code = StatusCode(kind="process", code=137, message="killed by SIGKILL")
    # Act
    verdict = code.final
    # Assert
    assert verdict is True


# EOF
