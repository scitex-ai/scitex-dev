"""Unit tests for scitex_dev.hosts._probe.

Covers: the ordered-pair denominator, asymmetry (A->B is not B->A), skips
being reported rather than dropped, and the rule that `pass` requires a
COMPLETE sweep.

NOT MOCKED. The injected runner really forks a process (`sh -c 'exit N'`)
and its real exit status is what the classifier reads, so argv construction,
exit-code interpretation and the counting are all exercised for real. The
only thing the seam replaces is which machine answers.
"""

from __future__ import annotations

from scitex_dev.hosts import (
    HostConnectivity,
    HostRecord,
    NetRoute,
    check_matrix,
    local_host_name,
    run_command,
)

_A = HostRecord(
    name="host-a",
    kind="compute",
    ssh_alias="host-a",
    scitex_root="~/.scitex",
    connectivity=HostConnectivity(lan="10.0.0.1"),
)
_B = HostRecord(
    name="host-b",
    kind="compute",
    ssh_alias="host-b",
    scitex_root="~/.scitex",
    connectivity=HostConnectivity(lan="10.0.0.2"),
)
_C = HostRecord(
    name="host-c",
    kind="storage",
    ssh_alias="host-c",
    scitex_root="~/.scitex",
    connectivity=HostConnectivity(
        lan="10.0.0.3", net=NetRoute(transport="cloudflared", hostname="c.example.com")
    ),
)


class RecordingRunner:
    """Runs a REAL local process; refuses the argvs matching `refuse`.

    An injected collaborator, not a mock: every call forks `sh -c 'exit N'`
    and the CommandResult is built from that process's actual status.
    """

    def __init__(self, refuse=()):
        self.refuse = tuple(refuse)
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv, *, timeout=10.0):
        joined = " ".join(str(a) for a in argv)
        self.calls.append(tuple(str(a) for a in argv))
        code = 255 if any(needle in joined for needle in self.refuse) else 0
        return run_command(["sh", "-c", f"exit {code}"], timeout=timeout)


# -------- the denominator -----------------------------------------------------


def test_expected_is_n_times_n_minus_one_per_transport():
    # Arrange — 3 hosts, 1 transport -> 3*2 = 6 ordered pairs.
    runner = RecordingRunner()
    # Act
    result = check_matrix([_A, _B, _C], transports=("lan",), runner=runner)
    # Assert
    assert result.expected == 6


def test_expected_counts_each_transport_separately():
    # Arrange
    runner = RecordingRunner()
    # Act
    result = check_matrix([_A, _B, _C], transports=("lan", "net"), runner=runner)
    # Assert
    assert result.expected == 12


def test_summary_names_the_denominator():
    """A bare pass count cannot be distinguished from a sweep that never ran."""
    # Arrange
    runner = RecordingRunner()
    # Act
    result = check_matrix([_A, _B], transports=("lan",), runner=runner)
    # Assert
    assert "of 2 ordered pairs" in result.summary_line()


# -------- ordered, not symmetric ---------------------------------------------


def test_a_pair_is_probed_in_both_directions():
    # Arrange
    runner = RecordingRunner()
    # Act
    result = check_matrix([_A, _B], transports=("lan",), runner=runner)
    # Assert
    assert {(p.source, p.target) for p in result.probes} == {
        ("host-a", "host-b"),
        ("host-b", "host-a"),
    }


def test_one_direction_can_fail_while_the_other_passes():
    """Different keys, different authorized_keys — A->B says nothing about B->A."""
    # Arrange — only the probe that RUNS ON host-b is refused.
    runner = RecordingRunner(refuse=("ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new host-b ssh",))
    # Act
    result = check_matrix([_A, _B], transports=("lan",), runner=runner)
    outcome = {(p.source, p.target): p.status for p in result.probes}
    # Assert
    assert outcome == {("host-a", "host-b"): "ok", ("host-b", "host-a"): "failed"}


def test_a_remote_source_runs_the_probe_through_that_source():
    """Otherwise the sweep measures OUR keys N times, not each host's."""
    # Arrange
    runner = RecordingRunner()
    # Act
    check_matrix([_A, _B], transports=("lan",), runner=runner)
    from_a = [c for c in runner.calls if "host-a" in c]
    # Assert
    assert any("host-b" in " ".join(call) for call in from_a)


# -------- skips are reported, never silently dropped -------------------------


def test_a_target_without_a_net_route_is_skipped():
    # Arrange — only host-c has a `net` route.
    runner = RecordingRunner()
    # Act
    result = check_matrix([_A, _B, _C], transports=("net",), runner=runner)
    # Assert
    assert result.skipped == 4


def test_a_skip_carries_its_reason():
    # Arrange
    runner = RecordingRunner()
    # Act
    result = check_matrix([_A, _B], transports=("net",), runner=runner)
    # Assert
    assert all("records no `net` route" in p.detail for p in result.probes)


def test_a_skip_is_not_an_attempt():
    # Arrange
    runner = RecordingRunner()
    # Act
    result = check_matrix([_A, _B], transports=("net",), runner=runner)
    # Assert
    assert result.attempted == 0


def test_a_skip_is_not_a_pass():
    # Arrange
    runner = RecordingRunner()
    # Act
    result = check_matrix([_A, _B], transports=("net",), runner=runner)
    # Assert
    assert result.ok == 0


# -------- verdict -------------------------------------------------------------


def test_a_complete_clean_sweep_passes():
    # Arrange
    runner = RecordingRunner()
    # Act
    result = check_matrix([_A, _B], transports=("lan",), runner=runner)
    # Assert
    assert result.verdict == "pass"


def test_a_mostly_skipped_sweep_is_incomplete_not_pass():
    """The failure this module exists to prevent, stated as a test."""
    # Arrange — every `net` probe skips; nothing fails.
    runner = RecordingRunner()
    # Act
    result = check_matrix([_A, _B], transports=("net",), runner=runner)
    # Assert
    assert result.verdict == "incomplete"


def test_any_failure_makes_the_verdict_fail():
    # Arrange
    runner = RecordingRunner(refuse=("host-b",))
    # Act
    result = check_matrix([_A, _B], transports=("lan",), runner=runner)
    # Assert
    assert result.verdict == "fail"


def test_a_transport_failure_says_ssh_could_not_connect():
    """255 is ssh's own status — 'could not get there', not 'command failed'."""
    # Arrange
    runner = RecordingRunner(refuse=("host-b",))
    # Act
    result = check_matrix([_A, _B], transports=("lan",), runner=runner)
    failed = [p for p in result.probes if p.status == "failed"]
    # Assert
    assert "ssh could not connect" in failed[0].detail


def test_to_dict_exposes_the_denominator():
    # Arrange
    runner = RecordingRunner()
    # Act
    payload = check_matrix([_A, _B], transports=("lan",), runner=runner).to_dict()
    # Assert
    assert payload["expected_ordered_pairs"] == 2


# -------- local host identification ------------------------------------------


def test_local_host_matches_a_reported_hostname():
    """The NAS boxes are keyed scitex-nas-01 and call themselves WATANAS1."""
    # Arrange
    nas = HostRecord(
        name="scitex-nas-01",
        kind="storage",
        ssh_alias="scitex-nas-01",
        scitex_root="~/.scitex",
        connectivity=HostConnectivity(lan="10.0.0.9", reported_hostname="WATANAS1"),
    )
    # Act
    found = local_host_name([nas], hostname="watanas1")
    # Assert
    assert found == "scitex-nas-01"


def test_an_unregistered_machine_is_not_claimed_to_be_one_of_the_fleet():
    """None inside a container — assuming otherwise misattributes results."""
    # Arrange
    # Act
    found = local_host_name([_A, _B], hostname="some-agent-container")
    # Assert
    assert found is None


# EOF
