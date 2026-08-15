#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The two quoting hops, and the refusal to treat an unroutable peer as rung.

The transport was verified end-to-end against the operator's laptop, which
proves the happy path and NOTHING about a hostile payload or an absent peer.
These cover what the wire test cannot.
"""

from __future__ import annotations

import shlex
import subprocess

import pytest

from scitex_dev.store._relay import TransportError
from scitex_dev.store._relay_ssh import SshPsqlTransport, aliases_for, ring_argv

ALIAS = "ywata-note-win"
CHANNEL = "scitex_store_public"
PAYLOAD = "scitex-compute-04:4477"


def _argv(payload: str = PAYLOAD) -> list[str]:
    return ring_argv(ALIAS, CHANNEL, payload)


def _remote_tokens(payload: str = PAYLOAD) -> list[str]:
    """Split the remote command the way the PEER'S SHELL will.

    Asserting on the raw string would test how :func:`shlex.quote` happens to
    nest its quotes. What actually matters is the token list the far side
    reconstructs, so the check runs the same reassembly.
    """
    return shlex.split(_argv(payload)[-1])


def test_the_alias_is_the_ssh_destination() -> None:
    # Arrange
    argv = _argv()
    # Act
    destination = argv[-2]
    # Assert
    assert destination == ALIAS


def test_the_sql_binds_variables_instead_of_interpolating() -> None:
    """``:'chan'`` quotes as a LITERAL; an f-string would not.

    The payload is small and tame today. "Tame today" is not a defence that
    survives someone widening the payload later.
    """
    # Arrange
    expected = "select pg_notify(:'chan', :'payload')"
    # Act
    tokens = _remote_tokens()
    # Assert
    assert tokens[-1] == expected


def test_the_payload_is_never_pasted_into_the_sql_text() -> None:
    # Arrange
    tokens = _remote_tokens()
    # Act
    sql = tokens[-1]
    # Assert
    assert PAYLOAD not in sql


def test_a_payload_bearing_a_quote_survives_the_shell_hop_as_data() -> None:
    """THERE ARE TWO HOPS, and fixing only the SQL one leaves the shell open.

    The argv is reassembled by the peer's login shell, so a value carrying a
    quote must arrive there as ONE token, unchanged.
    """
    # Arrange
    hostile = "a'b"
    # Act
    tokens = _remote_tokens(hostile)
    # Assert
    assert f"payload={hostile}" in tokens


def test_a_payload_bearing_a_shell_metacharacter_stays_one_token() -> None:
    """If quoting were broken this value would split, and the tail would RUN."""
    # Arrange
    hostile = "x; rm -rf ~"
    # Act
    tokens = _remote_tokens(hostile)
    # Assert
    assert f"payload={hostile}" in tokens


def test_psql_is_told_never_to_prompt() -> None:
    """A relay has no terminal to answer a password prompt on.

    Without ``-w`` an auth misconfiguration becomes a HANG rather than an
    error, and a hung ring is the failure shape this package exists to avoid.
    """
    # Arrange
    argv = _argv()
    # Act
    remote = argv[-1]
    # Assert
    assert " -w " in remote


def test_the_connection_is_multiplexed() -> None:
    """Measured: 425-485 ms cold per ring, 79-91 ms multiplexed.

    A hint is a latency optimisation, so a transport paying full key exchange
    per ring has spent the thing it was buying.
    """
    # Arrange
    argv = _argv()
    # Act
    joined = " ".join(argv)
    # Assert
    assert "ControlPersist=300" in joined


def test_the_ring_is_bounded_by_a_connect_timeout() -> None:
    # Arrange
    argv = _argv()
    # Act
    joined = " ".join(argv)
    # Assert
    assert "ConnectTimeout=5" in joined


def test_an_empty_alias_is_refused() -> None:
    # Arrange
    alias = ""
    # Act
    attempt = lambda: ring_argv(alias, CHANNEL, PAYLOAD)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="non-empty host alias"):
        attempt()


def test_a_peer_with_no_alias_raises_rather_than_being_skipped() -> None:
    """The registry declared the operator's laptop unroutable while ssh worked.

    A transport that skipped an unmapped peer would return a clean report
    having rung nobody.
    """
    # Arrange
    transport = SshPsqlTransport(aliases_for(["ywata-note-win"]))
    # Act
    attempt = lambda: transport.deliver("scitex-nas-03", CHANNEL, PAYLOAD)  # noqa: E731
    # Assert
    with pytest.raises(TransportError, match="no ssh alias declared"):
        attempt()


def test_a_non_zero_exit_is_a_transport_error() -> None:
    # Arrange
    def failing(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="could not connect")

    transport = SshPsqlTransport(aliases_for([ALIAS]), runner=failing)
    # Act
    attempt = lambda: transport.deliver(ALIAS, CHANNEL, PAYLOAD)  # noqa: E731
    # Assert
    with pytest.raises(TransportError, match="exited 2"):
        attempt()


def test_the_error_carries_the_last_line_of_stderr() -> None:
    """WHAT the peer said, not merely that it said something."""

    # Arrange
    def failing(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="x\nfe_sendauth: no password")

    transport = SshPsqlTransport(aliases_for([ALIAS]), runner=failing)
    # Act
    attempt = lambda: transport.deliver(ALIAS, CHANNEL, PAYLOAD)  # noqa: E731
    # Assert
    with pytest.raises(TransportError, match="fe_sendauth"):
        attempt()


def test_a_hung_peer_becomes_an_error_not_a_stall() -> None:
    """One hung peer must not stall the fan-out behind it."""

    # Arrange
    def hanging(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 10))

    transport = SshPsqlTransport(aliases_for([ALIAS]), runner=hanging)
    # Act
    attempt = lambda: transport.deliver(ALIAS, CHANNEL, PAYLOAD)  # noqa: E731
    # Assert
    with pytest.raises(TransportError, match="timed out"):
        attempt()


def test_a_missing_ssh_binary_is_a_transport_error() -> None:
    # Arrange
    def absent(argv, **kwargs):
        raise FileNotFoundError("ssh")

    transport = SshPsqlTransport(aliases_for([ALIAS]), runner=absent)
    # Act
    attempt = lambda: transport.deliver(ALIAS, CHANNEL, PAYLOAD)  # noqa: E731
    # Assert
    with pytest.raises(TransportError, match="could not launch ssh"):
        attempt()


def test_a_successful_ring_raises_nothing() -> None:
    """The positive control.

    Every other test here asserts a refusal; without this one, a transport that
    refused EVERYTHING would pass them all.
    """

    # Arrange
    def ok(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    transport = SshPsqlTransport(aliases_for([ALIAS]), runner=ok)
    # Act
    result = transport.deliver(ALIAS, CHANNEL, PAYLOAD)
    # Assert
    assert result is None


def test_aliases_for_maps_a_peer_to_itself() -> None:
    # Arrange
    peers = ["a", "b"]
    # Act
    mapping = aliases_for(peers)
    # Assert
    assert mapping == {"a": "a", "b": "b"}


# EOF
