#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The fan-out contract: an unreachable peer must be REPORTED, never skipped.

The failure these pin is not "the relay crashed". It is the relay that returns
cleanly having rung nobody — because the hint was not its own, because no peer
was declared, or because the one peer that mattered was unreachable and the
loop moved on. All three look identical from outside unless the report names
them, and this fleet has already been bitten by each shape.
"""

from __future__ import annotations

import pytest

from scitex_dev.store._notify import Hint, channel_for, encode_hint
from scitex_dev.store._relay import (
    InMemoryTransport,
    RelayOutcome,
    TransportError,
    fan_out,
)

NODE = "scitex-compute-04"
PEERS = ("ywata-note-win", "scitex-nas-03")


def _hint(origin: str = NODE, max_seq: int = 4477) -> Hint:
    return Hint(origin=origin, max_seq=max_seq)


def test_every_peer_is_rung() -> None:
    # Arrange
    transport = InMemoryTransport()
    # Act
    report = fan_out(_hint(), node_id=NODE, peers=PEERS, transport=transport)
    # Assert
    assert [peer for peer, _, _ in transport.rung] == list(PEERS)


def test_the_report_marks_a_successful_fan_out_as_forwarded() -> None:
    # Arrange
    transport = InMemoryTransport()
    # Act
    report = fan_out(_hint(), node_id=NODE, peers=PEERS, transport=transport)
    # Assert
    assert report.forwarded is True


def test_the_payload_rung_is_the_encoded_hint() -> None:
    """The peer must receive the SAME payload, not a re-derived one.

    A relay that rebuilt the payload from its own state would announce its own
    sequence under the originating node's name — a hint pointing at ops that
    peer does not have.
    """
    # Arrange
    transport = InMemoryTransport()
    # Act
    fan_out(_hint(max_seq=91), node_id=NODE, peers=("a",), transport=transport)
    # Assert
    assert transport.rung[0][2] == encode_hint(NODE, 91)


def test_the_peer_is_rung_on_its_own_store_channel() -> None:
    """ONE CHANNEL PER STORE, and the peer's listeners subscribe to theirs.

    Ringing a relay-specific channel would be heard by nobody, and would look
    exactly like a successful delivery from this side.
    """
    # Arrange
    transport = InMemoryTransport()
    # Act
    fan_out(_hint(), node_id=NODE, peers=("a",), transport=transport, schema_name="cards")
    # Assert
    assert transport.rung[0][1] == channel_for("cards")


def test_a_hint_from_another_node_is_not_forwarded() -> None:
    """LOOP SUPPRESSION.

    Every host rings every peer directly, so a host that re-forwarded what it
    received would multiply each write by the fleet size.
    """
    # Arrange
    transport = InMemoryTransport()
    # Act
    report = fan_out(
        _hint(origin="scitex-nas-01"), node_id=NODE, peers=PEERS, transport=transport
    )
    # Assert
    assert (report.forwarded, transport.rung) == (False, [])


def test_a_foreign_hint_reports_why_it_was_not_forwarded() -> None:
    """Suppression must be VISIBLE, or it is indistinguishable from a no-op."""
    # Arrange
    transport = InMemoryTransport()
    # Act
    report = fan_out(
        _hint(origin="scitex-nas-01"), node_id=NODE, peers=PEERS, transport=transport
    )
    # Assert
    assert report.reason == "origin-is-not-this-node"


def test_a_relay_with_no_peers_is_reported_not_treated_as_success() -> None:
    """THE QUIETEST FAILURE IN THIS PACKAGE.

    The host registry declared the operator's laptop with no ssh route while
    ssh to it worked in both directions. A relay that read that record would
    ring nobody and return an empty, error-free result.
    """
    # Arrange
    transport = InMemoryTransport()
    # Act
    report = fan_out(_hint(), node_id=NODE, peers=(), transport=transport)
    # Assert
    assert (report.forwarded, report.reason) == (False, "no-peers-declared")


def test_an_unreachable_peer_does_not_stop_the_reachable_ones() -> None:
    """Partial reachability is this fleet's NORMAL state.

    nas-03 is off the overlay and the laptop sleeps. A fan-out that aborted on
    the first failure would let one unreachable host silence every other.
    """
    # Arrange
    transport = InMemoryTransport(unreachable=("scitex-nas-03",))
    # Act
    fan_out(_hint(), node_id=NODE, peers=("scitex-nas-03", "ywata-note-win"), transport=transport)
    # Assert
    assert [peer for peer, _, _ in transport.rung] == ["ywata-note-win"]


def test_an_unreachable_peer_is_reported_as_undelivered() -> None:
    # Arrange
    transport = InMemoryTransport(unreachable=("scitex-nas-03",))
    # Act
    report = fan_out(
        _hint(), node_id=NODE, peers=("scitex-nas-03", "ywata-note-win"), transport=transport
    )
    # Assert
    assert [o.peer for o in report.undelivered] == ["scitex-nas-03"]


def test_the_failure_detail_names_the_cause() -> None:
    """"Something went wrong" is not actionable at 02:00.

    The peer name is already in the outcome; the detail must add the REASON.
    """
    # Arrange
    transport = InMemoryTransport(unreachable=("scitex-nas-03",))
    # Act
    report = fan_out(_hint(), node_id=NODE, peers=("scitex-nas-03",), transport=transport)
    # Assert
    assert report.undelivered[0].detail.startswith("TransportError:")


def test_a_transport_raising_an_unforeseen_type_is_still_reported() -> None:
    """The catch is broad ON PURPOSE — transports are pluggable.

    A narrow catch would let an unnamed exception type abort the loop and take
    every reachable peer down with the unreachable one.
    """

    class OddTransport:
        def deliver(self, peer: str, channel: str, payload: str) -> None:
            raise ZeroDivisionError("a driver nobody anticipated")

    # Arrange
    transport = OddTransport()
    # Act
    report = fan_out(_hint(), node_id=NODE, peers=("a", "b"), transport=transport)
    # Assert
    assert [o.delivered for o in report.outcomes] == [False, False]


def test_a_fully_delivered_fan_out_has_nothing_undelivered() -> None:
    """The positive control: `undelivered` must be able to be empty.

    Without this, a property that always reported something would satisfy
    every failure test above and be useless.
    """
    # Arrange
    transport = InMemoryTransport()
    # Act
    report = fan_out(_hint(), node_id=NODE, peers=PEERS, transport=transport)
    # Assert
    assert report.undelivered == ()


def test_an_outcome_defaults_to_an_empty_detail() -> None:
    # Arrange
    outcome = RelayOutcome(peer="a", delivered=True)
    # Act
    detail = outcome.detail
    # Assert
    assert detail == ""


def test_the_in_memory_transport_raises_for_a_peer_it_cannot_reach() -> None:
    """It is a REAL transport, so its failure is a real TransportError."""
    # Arrange
    transport = InMemoryTransport(unreachable=("gone",))
    # Act
    attempt = lambda: transport.deliver("gone", "chan", "a:1")  # noqa: E731
    # Assert
    with pytest.raises(TransportError, match="not reachable"):
        attempt()


# EOF
