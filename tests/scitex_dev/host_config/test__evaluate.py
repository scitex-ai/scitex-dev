#!/usr/bin/env python3
"""Does ``root=`` actually contain the evaluation?

`evaluate()` takes ``root`` so a caller can grade a tree it controls
instead of the real ``/etc``. That promise is only worth as much as its
leakiest line: on 2026-08-16 develop went red at 08092b69 because
``requires_command`` was checked with ``shutil.which()`` OUTSIDE the
``root == "/"`` guard, so a spec written into ``tmp_path`` was judged by
whichever machine happened to run the test.

It presented as a Python-version failure, which it was not:

    py3.11   scitex-02-org-cpu-01   pass
    py3.12   scitex-04-org-cpu-01   pass
    py3.13   spartan-cpu-org-01     FAIL

Three legs, three different machines. The dhcp specs require
``networkctl``; the scitex-* hosts run systemd-networkd and Spartan does
not. Version was confounded with machine.

Nothing pinned that branch before this file. The only test naming
``requires_command`` asserts the specs DECLARE one -- not that the check
ever fires -- so the guard could have been deleted outright and the suite
would have stayed green. Hence a PAIR: tests that it no longer fires
where it must not, and tests that it still does fire where it must.

No mocks (STX-NM002): the absent command is absent because nothing on any
PATH is named it, and the present one is `sh`. Both are asserted rather
than assumed.
"""

import shutil

import pytest

from scitex_dev.host_config import (
    STATE_PRECONDITION_UNMET,
    HostConfigSpec,
    evaluate,
)

#: A name no PATH will contain. Asserted absent below -- a control that
#: quietly stopped controlling is the failure mode this file exists for.
ABSENT_COMMAND = "scitex-dev-no-such-binary-8f3a1c"

#: The distinctive half of the requires_command message. Tests assert on
#: THIS rather than on the state, because volatility can return the same
#: state for an unrelated reason and would make an assertion pass for the
#: wrong cause on a RAM-backed /etc.
NOT_INSTALLED = "is not installed"

SPEC_PATH = "/etc/scitex-dev-guard.conf"


def _spec(requires_command):
    return HostConfigSpec(
        name="test.guard",
        path=SPEC_PATH,
        content="# scitex-dev test\n",
        purpose="pin whether root= contains the evaluation",
        provider="scitex-dev",
        requires_command=requires_command,
    )


@pytest.fixture
def synthetic_root_status(tmp_path):
    """Grade a converged tree under ``tmp_path``, requiring an absent binary."""
    spec = _spec(ABSENT_COMMAND)
    target = tmp_path / SPEC_PATH.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(spec.content)
    target.chmod(0o644)
    return evaluate(spec, root=str(tmp_path), hostname="any-host")


@pytest.fixture
def real_root_absent_status():
    """Grade the REAL host, requiring an absent binary.

    Returns before touching the filesystem, so it reads no real ``/etc``
    despite naming a path under it.
    """
    return evaluate(_spec(ABSENT_COMMAND), root="/", hostname="any-host")


@pytest.fixture
def real_root_present_status():
    """Grade the REAL host, requiring a binary that always exists."""
    return evaluate(_spec("sh"), root="/", hostname="any-host")


def test_the_absent_command_really_is_absent():
    """CONTROL FOR THE CONTROL.

    Every expectation of ``precondition_unmet`` below is vacuous if this
    name happens to resolve. Assert it rather than trusting it.
    """
    # Arrange
    name = ABSENT_COMMAND
    # Act
    resolved = shutil.which(name)
    # Assert
    assert resolved is None


def test_sh_really_is_present():
    """CONTROL FOR THE POSITIVE CONTROL, for the same reason."""
    # Arrange
    name = "sh"
    # Act
    resolved = shutil.which(name)
    # Assert
    assert resolved is not None


def test_a_synthetic_root_does_not_report_a_missing_binary(synthetic_root_status):
    """THE REGRESSION, 2026-08-16.

    Under a synthetic root the question is about the TREE, not the host,
    so the machine's PATH must not appear in the verdict at all.
    """
    # Arrange
    status = synthetic_root_status
    # Act
    detail = status.detail
    # Assert
    assert NOT_INSTALLED not in detail


def test_a_converged_synthetic_tree_is_not_precondition_unmet(synthetic_root_status):
    """The other half: a file written exactly as declared reads back as
    converged on EVERY machine, including one without the daemon."""
    # Arrange
    status = synthetic_root_status
    # Act
    state = status.state
    # Assert
    assert state != STATE_PRECONDITION_UNMET


def test_the_precondition_still_fires_on_the_real_host(real_root_absent_status):
    """NEGATIVE CONTROL -- the guard must not have deleted the check.

    With ``root="/"`` the machine IS the subject of the question, so a
    missing binary is the finding the field was added for: a file that
    would be present, correct, and read by nothing.
    """
    # Arrange
    status = real_root_absent_status
    # Act
    state = status.state
    # Assert
    assert state == STATE_PRECONDITION_UNMET


def test_the_real_host_verdict_names_the_missing_binary(real_root_absent_status):
    """And it fires for the RIGHT reason -- volatility returns the same
    state, so the state alone cannot tell the two causes apart."""
    # Arrange
    status = real_root_absent_status
    # Act
    detail = status.detail
    # Assert
    assert NOT_INSTALLED in detail


def test_a_present_command_does_not_trip_the_precondition(real_root_present_status):
    """POSITIVE CONTROL -- the check discriminates rather than always firing.

    Asserted on the message and not the state: volatility runs next and
    can legitimately return ``precondition_unmet`` for a RAM-backed path,
    which would let this pass for the wrong reason.
    """
    # Arrange
    status = real_root_present_status
    # Act
    detail = status.detail
    # Assert
    assert NOT_INSTALLED not in detail
