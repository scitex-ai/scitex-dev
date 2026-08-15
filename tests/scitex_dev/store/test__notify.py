#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The doorbell contract: hints are lost routinely, so losing one must be cheap.

Every assertion here traces to one of two measurements scitex-cards took on the
live store, 2026-08-15:

    0.38 ms delivery
    0 of 3 notifications survive a disconnected listener
    0 delivered when the emitting transaction ROLLS BACK

The first says push is worth having. The second says it can never be trusted for
delivery. The third says a hint can never precede the data, which is what lets
the emit sit on the write path with no outbox.
"""

from __future__ import annotations

import pytest

from scitex_dev.store._notify import (
    Hint,
    channel_for,
    decode_hint,
    encode_hint,
)


def test_the_channel_is_named_per_store() -> None:
    """ONE CHANNEL PER STORE, NOT PER ORIGIN.

    Per-origin would require a listener to know the origin set in advance to
    subscribe, so a NEW peer's first write is heard by nobody — silent, and
    landing precisely on the case the doorbell exists for.
    """
    # Arrange
    schema_name = "public"
    # Act
    channel = channel_for(schema_name)
    # Assert
    assert channel == "scitex_store_public"


def test_two_schemas_get_two_channels() -> None:
    # Arrange
    first, second = "public", "cards"
    # Act
    channels = {channel_for(first), channel_for(second)}
    # Assert
    assert len(channels) == 2


def test_a_hint_round_trips() -> None:
    # Arrange
    origin, max_seq = "scitex-compute-04", 4477
    # Act
    decoded = decode_hint(encode_hint(origin, max_seq))
    # Assert
    assert decoded == Hint(origin=origin, max_seq=max_seq)


def test_an_origin_containing_a_colon_is_refused() -> None:
    """A WRONG-BUT-PARSEABLE HINT IS WORSE THAN A REJECTED ONE.

    The payload splits on the first colon, so `a:b` as an origin would decode
    to origin `a` with a mangled sequence — sending a listener to sweep a peer
    that does not exist while the real one waits for the next tick.
    """
    # Arrange
    origin = "host:with:colons"
    # Act
    attempt = lambda: encode_hint(origin, 1)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="may not contain"):
        attempt()


def test_an_empty_origin_is_refused() -> None:
    # Arrange
    origin = ""
    # Act
    attempt = lambda: encode_hint(origin, 1)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="non-empty node id"):
        attempt()


def test_an_oversized_payload_is_refused_rather_than_truncated() -> None:
    """NOTIFY's ceiling is 8000 bytes and truncation is silent.

    A truncated hint still LOOKS like a hint, so the failure would present as a
    listener sweeping the wrong peer rather than as an error.
    """
    # Arrange
    origin = "x" * 8001
    # Act
    attempt = lambda: encode_hint(origin, 1)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="ceiling"):
        attempt()


@pytest.mark.parametrize(
    "payload",
    ["", "no-colon", ":5", "origin:", "origin:notanumber", "origin:-1"],
)
def test_an_unreadable_payload_decodes_to_none_rather_than_raising(
    payload: str,
) -> None:
    """A DEAD LISTENER STOPS SWEEPING.

    Listeners receive whatever is on the channel, including payloads from a
    future version of this contract. Raising would kill the listener and turn a
    cosmetic incompatibility into a convergence failure — so unreadable decodes
    to None, which a caller treats exactly like a hint it never received.
    """
    # Arrange
    received = payload
    # Act
    hint = decode_hint(received)
    # Assert
    assert hint is None


def test_the_payload_carries_no_data_beyond_origin_and_sequence() -> None:
    """THE PAYLOAD IS A HINT, NEVER THE DATA.

    Pinned as a shape assertion because the temptation to "just add the row,
    it's only a few bytes" is exactly how a lost notification becomes lost data
    — and notifications ARE lost, 3 times out of 3 when the listener is away.
    """
    # Arrange
    encoded = encode_hint("scitex-compute-01", 12)
    # Act
    fields = encoded.split(":")
    # Assert
    assert fields == ["scitex-compute-01", "12"]


def test_a_zero_sequence_is_legal() -> None:
    """An empty oplog is a real state, not an error.

    Refusing 0 would make a fresh node unable to ring the doorbell at all,
    which is the one moment its peers most need to notice it.
    """
    # Arrange
    origin = "fresh-node"
    # Act
    hint = decode_hint(encode_hint(origin, 0))
    # Assert
    assert hint == Hint(origin=origin, max_seq=0)


# EOF
