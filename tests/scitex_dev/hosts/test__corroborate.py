"""Unit tests for scitex_dev.hosts._corroborate.

The rule under test: an address is rewritten ONLY when all three independent
signals agree. Anything less is `insufficient` or `conflict`, never a pass —
"no contradiction found" is not corroboration, and that conflation is the
single most repeated defect in this fleet's tooling.

NOT MOCKED. The injected runner forks a real `sh -c` that prints the scripted
stdout and exits with the scripted status, so the parsing, the MAC/fingerprint
normalisation and the verdict arithmetic are all exercised against real
process output. Only which machine answers is substituted.
"""

from __future__ import annotations

import shlex

from scitex_dev.hosts import (
    REQUIRED_SIGNALS,
    HostConnectivity,
    HostRecord,
    corroborate,
    run_command,
)

_FINGERPRINT = "SHA256:AbCdEfGh0123456789+/xyzABCDEfghIJKLmnopQRS"
_MAC = "70:85:c2:3a:a9:42"

_FULL = HostRecord(
    name="scitex-compute-01",
    kind="compute",
    ssh_alias="scitex-compute-01",
    scitex_root="~/.scitex",
    connectivity=HostConnectivity(
        lan="192.168.11.94",
        reserved="192.168.11.171",
        mac=_MAC,
        host_key_fingerprint=_FINGERPRINT,
        reported_hostname="scitex-compute-01",
    ),
)

_NO_MAC = HostRecord(
    name="scitex-compute-04",
    kind="compute",
    ssh_alias="scitex-compute-04",
    scitex_root="~/.scitex",
    connectivity=HostConnectivity(
        lan="192.168.11.164",
        host_key_fingerprint=_FINGERPRINT,
        reported_hostname="scitex-compute-04",
    ),
)


class ScriptedRunner:
    """Forks a REAL process that prints the scripted stdout and exits.

    Keyed by the binary being invoked. An unscripted binary answers 127 —
    the same status the real runner reports for a tool that is not
    installed, which is the ordinary state of `ip` and `arp` inside the
    fleet's agent containers.
    """

    def __init__(self, **responses):
        self.responses = responses

    def __call__(self, argv, *, timeout=10.0):
        binary = str(argv[0]).replace("-", "_")
        rc, out = self.responses.get(binary, (127, ""))
        script = f"printf '%s' {shlex.quote(out)}; exit {rc}"
        return run_command(["sh", "-c", script], timeout=timeout)


def _all_agreeing(hostname="scitex-compute-01", mac=_MAC, fingerprint=_FINGERPRINT):
    return ScriptedRunner(
        ip=(0, f"192.168.11.94 dev eth0 lladdr {mac} REACHABLE\n"),
        ssh_keyscan=(0, "192.168.11.94 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5\n"),
        ssh_keygen=(0, f"256 {fingerprint} root@host (ED25519)\n"),
        ssh=(0, f"{hostname}\n"),
    )


# -------- the contract --------------------------------------------------------


def test_three_signals_are_required():
    """Pinned, so weakening the rule to two is a deliberate reviewed act."""
    # Arrange
    # Act
    required = REQUIRED_SIGNALS
    # Assert
    assert len(required) == 3


# -------- all three agree -> safe to rewrite ---------------------------------


def test_all_three_agreeing_is_corroborated():
    # Arrange
    runner = _all_agreeing()
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert result.verdict == "corroborated"


def test_all_three_agreeing_permits_the_rewrite():
    # Arrange
    runner = _all_agreeing()
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert result.may_rewrite is True


def test_a_corroborated_result_has_nothing_to_escalate():
    # Arrange
    runner = _all_agreeing()
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert result.escalation() is None


# -------- any disagreement -> conflict, never a silent decision ---------------


def test_a_different_host_key_is_a_conflict():
    """The strongest signal disagreeing: a DIFFERENT box now answers here."""
    # Arrange
    runner = _all_agreeing(fingerprint="SHA256:SomeOtherMachineEntirely00000000000000000")
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert result.verdict == "conflict"


def test_a_conflict_refuses_the_rewrite():
    # Arrange
    runner = _all_agreeing(fingerprint="SHA256:SomeOtherMachineEntirely00000000000000000")
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert result.may_rewrite is False


def test_a_conflict_escalates_to_a_human():
    """A machine can detect disagreement; it cannot decide which source is true."""
    # Arrange
    runner = _all_agreeing(mac="aa:bb:cc:dd:ee:ff")
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert "CONFLICT" in (result.escalation() or "")


def test_every_signal_still_runs_after_the_first_disagreement():
    """An escalation is worth more with the whole picture attached."""
    # Arrange
    runner = _all_agreeing(mac="aa:bb:cc:dd:ee:ff")
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert len(result.available) == 3


def test_a_machine_calling_itself_something_else_is_a_conflict():
    # Arrange
    runner = _all_agreeing(hostname="somebody-elses-laptop")
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert result.verdict == "conflict"


# -------- fewer than three signals -> insufficient, NOT a pass ---------------


def test_a_missing_registry_mac_makes_the_signal_unavailable():
    # Arrange — scitex-compute-04 has no `mac:` recorded.
    runner = _all_agreeing(hostname="scitex-compute-04")
    # Act
    result = corroborate(_NO_MAC, runner=runner)
    # Assert
    assert "mac-reservation" in result.missing


def test_two_agreeing_signals_are_not_corroboration():
    """THE test. Nothing contradicted the address; that is not evidence for it."""
    # Arrange
    runner = _all_agreeing(hostname="scitex-compute-04")
    # Act
    result = corroborate(_NO_MAC, runner=runner)
    # Assert
    assert result.verdict == "insufficient"


def test_insufficient_refuses_the_rewrite():
    # Arrange
    runner = _all_agreeing(hostname="scitex-compute-04")
    # Act
    result = corroborate(_NO_MAC, runner=runner)
    # Assert
    assert result.may_rewrite is False


def test_the_summary_names_what_was_not_checked():
    # Arrange
    runner = _all_agreeing(hostname="scitex-compute-04")
    # Act
    result = corroborate(_NO_MAC, runner=runner)
    # Assert
    assert "NOT CHECKED: mac-reservation" in result.summary_line()


def test_a_missing_tool_is_unavailable_not_a_mismatch():
    """Neither `ip` nor `arp` exists in the agent containers. That is
    'we do not know', which must not read as a conflict OR as agreement."""
    # Arrange — every binary unscripted except the ones we script.
    runner = ScriptedRunner(
        ssh_keyscan=(0, "192.168.11.94 ssh-ed25519 AAAA\n"),
        ssh_keygen=(0, f"256 {_FINGERPRINT} root@host (ED25519)\n"),
        ssh=(0, "scitex-compute-01\n"),
    )
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert result.verdict == "insufficient"


def test_an_unreachable_host_is_insufficient_not_conflict():
    # Arrange — nothing answers at all.
    runner = ScriptedRunner()
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert result.verdict == "insufficient"


def test_a_host_with_no_address_has_nothing_to_check():
    # Arrange
    bare = HostRecord(
        name="mba", kind="workstation", ssh_alias="mba", scitex_root="~/.scitex"
    )
    # Act
    result = corroborate(bare, runner=_all_agreeing())
    # Assert
    assert result.verdict == "insufficient"


# -------- reserved vs observed is a NOTE, not a conflict ---------------------


def test_an_unrenewed_lease_is_reported_as_a_note():
    # Arrange — measured 2026-08-13: reserved .171, answering at .94.
    runner = _all_agreeing()
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert any("lease has not renewed" in note for note in result.notes)


def test_an_unrenewed_lease_does_not_block_the_rewrite():
    """Both facts are true. A reservation nobody claimed is not a disagreement
    about WHICH MACHINE is at the observed address."""
    # Arrange
    runner = _all_agreeing()
    # Act
    result = corroborate(_FULL, runner=runner)
    # Assert
    assert result.may_rewrite is True


# -------- explicit address ----------------------------------------------------


def test_an_explicit_address_overrides_the_recorded_one():
    # Arrange — ask about the RESERVATION instead of the observed address.
    runner = _all_agreeing()
    # Act
    result = corroborate(_FULL, "192.168.11.171", runner=runner)
    # Assert
    assert result.proposed_address == "192.168.11.171"


def test_to_dict_carries_the_may_rewrite_decision():
    # Arrange
    runner = _all_agreeing()
    # Act
    payload = corroborate(_FULL, runner=runner).to_dict()
    # Assert
    assert payload["may_rewrite"] is True


# EOF
