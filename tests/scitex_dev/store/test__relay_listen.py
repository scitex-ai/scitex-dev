#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A reconnecting relay must announce UNCONDITIONALLY, and never die on junk.

Both properties come from the same measurement: 0 of 3 notifications survive a
disconnected listener. Nothing tells a relay what it missed, so it cannot be
clever about whether to speak up, and it cannot afford to stop listening.
"""

from __future__ import annotations

from scitex_dev.store._notify import encode_hint
from scitex_dev.store._relay import InMemoryTransport
from scitex_dev.store._relay_listen import RelayListener

NODE = "scitex-compute-04"
PEERS = ("ywata-note-win",)


def _listener(transport: InMemoryTransport, **kwargs: object) -> RelayListener:
    return RelayListener(
        node_id=NODE, peers=PEERS, transport=transport, **kwargs  # type: ignore[arg-type]
    )


def test_a_local_hint_is_carried_to_the_peer() -> None:
    # Arrange
    transport = InMemoryTransport()
    listener = _listener(transport)
    # Act
    listener.handle(encode_hint(NODE, 4477))
    # Assert
    assert transport.rung[0][2] == encode_hint(NODE, 4477)


def test_a_hint_from_another_node_is_not_carried_onward() -> None:
    """Loop suppression holds through the listener, not only in `fan_out`."""
    # Arrange
    transport = InMemoryTransport()
    listener = _listener(transport)
    # Act
    listener.handle(encode_hint("scitex-nas-01", 12))
    # Assert
    assert transport.rung == []


def test_an_unreadable_payload_does_not_raise() -> None:
    """A relay that died on junk would stop carrying every good hint after it."""
    # Arrange
    transport = InMemoryTransport()
    listener = _listener(transport)
    # Act
    report = listener.handle("this is not a hint")
    # Assert
    assert report.reason == "undecodable-payload"


def test_the_listener_keeps_working_after_an_unreadable_payload() -> None:
    """THE POINT of not raising, stated as a test.

    Tolerating junk is worthless if the next real hint is not carried.
    """
    # Arrange
    transport = InMemoryTransport()
    listener = _listener(transport)
    listener.handle("garbage")
    # Act
    listener.handle(encode_hint(NODE, 5))
    # Assert
    assert len(transport.rung) == 1


def test_announce_rings_peers_with_this_nodes_position() -> None:
    """The reconnect path, which no incoming payload triggers."""
    # Arrange
    transport = InMemoryTransport()
    listener = _listener(transport)
    # Act
    listener.announce(4477)
    # Assert
    assert transport.rung[0][2] == encode_hint(NODE, 4477)


def test_announce_takes_no_has_anything_changed_argument() -> None:
    """DELIBERATE ABSENCE, pinned so nobody helpfully adds one.

    A reconnecting relay cannot know whether it missed anything — the state it
    would consult is updated by the notifications it missed. A conditional
    announce would stay silent in exactly the case it exists for.
    """
    # Arrange
    transport = InMemoryTransport()
    listener = _listener(transport)
    # Act
    parameters = RelayListener.announce.__code__.co_varnames[
        : RelayListener.announce.__code__.co_argcount
    ]
    # Assert
    assert parameters == ("self", "max_seq")


def test_an_unreachable_peer_is_reported_through_the_listener() -> None:
    # Arrange
    transport = InMemoryTransport(unreachable=("ywata-note-win",))
    listener = _listener(transport)
    # Act
    report = listener.handle(encode_hint(NODE, 1))
    # Assert
    assert [o.peer for o in report.undelivered] == ["ywata-note-win"]


def test_the_schema_choice_reaches_the_ring() -> None:
    # Arrange
    transport = InMemoryTransport()
    listener = _listener(transport, schema_name="cards")
    # Act
    listener.announce(3)
    # Assert
    assert transport.rung[0][1] == "scitex_store_cards"


# EOF
