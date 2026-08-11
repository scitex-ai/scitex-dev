#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the exchange id.

Every A->B gets an id, issued by B and returned in the immediate ack. It is
what makes "poll for status" point at something. Measured 2026-08-11: a spawn
client gave up at 30 s and reported a peer failure while the server worked the
request for 5 min 12 s — the client held no handle with which to re-ask, so a
guess was the only output available to it.

The id carries its origin host and its time ON PURPOSE: an agent on compute-04
asking the laptop about an exchange quotes the same string, so the value must
not depend on local context to be meaningful.
"""

from __future__ import annotations

from scitex_dev.status import EXCHANGE_ID_PATTERN, is_exchange_id, new_exchange_id


def test_a_new_exchange_id_matches_the_specified_format():
    """The format is normative; other languages parse the same string."""
    # Arrange
    identifier = new_exchange_id(host="scitex-compute-04")
    # Act
    matched = EXCHANGE_ID_PATTERN.match(identifier)
    # Assert
    assert matched is not None


def test_a_new_exchange_id_carries_its_origin_host():
    """Attribution travels with the id so a peer can tell who issued it."""
    # Arrange
    identifier = new_exchange_id(host="scitex-compute-04")
    # Act
    carried = "scitex-compute-04" in identifier
    # Assert
    assert carried is True


def test_a_new_exchange_id_starts_with_the_xch_prefix():
    """A recognisable prefix makes the value greppable in any log."""
    # Arrange
    identifier = new_exchange_id(host="laptop")
    # Act
    prefix = identifier[:4]
    # Assert
    assert prefix == "xch_"


def test_two_exchange_ids_minted_together_differ():
    """Ids are unique without coordination between hosts."""
    # Arrange
    first = new_exchange_id(host="laptop")
    # Act
    second = new_exchange_id(host="laptop")
    # Assert
    assert first != second


def test_unsafe_host_characters_are_replaced_rather_than_dropped():
    """Dropping them would let two different hosts collapse to one prefix."""
    # Arrange
    identifier = new_exchange_id(host="lab pc/01")
    # Act
    carried = "lab-pc-01" in identifier
    # Assert
    assert carried is True


def test_an_id_with_unsafe_host_characters_still_matches_the_format():
    """Sanitising must produce a value that still parses everywhere."""
    # Arrange
    identifier = new_exchange_id(host="lab pc/01")
    # Act
    matched = EXCHANGE_ID_PATTERN.match(identifier)
    # Assert
    assert matched is not None


def test_a_bare_uuid_is_not_accepted_as_an_exchange_id():
    """A uuid is unique but says nothing about origin or time."""
    # Arrange
    candidate = "6f1b2c3d-4e5f-6789-abcd-ef0123456789"
    # Act
    verdict = is_exchange_id(candidate)
    # Assert
    assert verdict is False


def test_a_non_string_is_not_accepted_as_an_exchange_id():
    """The check must refuse the type, not raise on it."""
    # Arrange
    candidate = 12345
    # Act
    verdict = is_exchange_id(candidate)
    # Assert
    assert verdict is False


def test_a_minted_id_is_recognised_by_the_checker():
    """The minter and the checker must agree, or neither is usable."""
    # Arrange
    identifier = new_exchange_id(host="scitex-compute-04")
    # Act
    verdict = is_exchange_id(identifier)
    # Assert
    assert verdict is True


# EOF
