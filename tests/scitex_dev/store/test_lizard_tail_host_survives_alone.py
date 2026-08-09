#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The lizard-tail rule.

Operator requirement, 2026-08-09: *a single host must keep working ALONE
when severed from every other host. No single point of failure. A host can
be added or dropped without ceremony, and the survivors keep going.*

This is a property of the DESIGN, not a feature bolted on: every host owns
a complete local store and writes to it without consulting anyone. There is
no coordinator, no quorum, no lock server and no "primary". Replication is
something a host does WITH a peer when one happens to be reachable, never
something it needs PERMISSION from a peer to proceed.

So severing a host degrades exactly one thing — how current its copy of
other hosts' data is — and nothing else. Its own writes keep working, its
own reads keep working, and when a peer returns, replay resumes at the
cursor with no repair step.

The tests below are deliberately about the ABSENCE of ceremony. There is no
`join()`, no `leave()`, no `register_host()`, and these assert that none is
needed rather than that some exist.
"""

from __future__ import annotations

from scitex_dev.store import NEW_RECORD, sync


def test_a_lone_host_can_write_with_no_peers_configured(local):
    """A store with no peers writes normally. Nothing to consult."""
    # Arrange
    values = {"id": "solo-1", "status": "open"}

    # Act
    result = local.put(values, expected_revision=NEW_RECORD)

    # Assert
    assert result.created is True


def test_a_lone_host_can_read_back_what_it_wrote(local):
    """Reads do not consult peers either."""
    # Arrange
    local.put({"id": "solo-1", "status": "open"}, expected_revision=NEW_RECORD)

    # Act
    row = local.get({"id": "solo-1"})

    # Assert
    assert row.values["status"] == "open"


def test_a_severed_host_keeps_accepting_writes(local, peer):
    """After a peer goes away mid-life, the survivor is unaffected.

    Closing the peer's connection is this suite's severance: any call into
    it would now fail, exactly as an unreachable host would.
    """
    # Arrange
    local.put({"id": "before", "status": "open"}, expected_revision=NEW_RECORD)
    peer.put({"id": "peer-row", "status": "open"}, expected_revision=NEW_RECORD)
    sync(local, peer)
    peer.close()

    # Act
    result = local.put({"id": "after", "status": "open"}, expected_revision=NEW_RECORD)

    # Assert
    assert result.created is True


def test_a_severed_host_keeps_the_data_it_replayed_before_the_split(local, peer):
    """What was already replayed stays. Severance loses currency, not data."""
    # Arrange
    peer.put({"id": "peer-row", "status": "open"}, expected_revision=NEW_RECORD)
    sync(local, peer)

    # Act
    peer.close()

    # Assert
    assert local.get({"id": "peer-row"}) is not None


def test_a_returning_peer_resumes_from_the_cursor_without_repair(local, make_store):
    """Reconnection needs no repair step — the cursor already knows."""
    # Arrange
    peer = make_store("peer")
    peer.put({"id": "p1"}, expected_revision=NEW_RECORD)
    sync(local, peer)
    peer.close()
    returned = make_store("peer")
    returned.put({"id": "p2"}, expected_revision=NEW_RECORD)

    # Act
    results = sync(local, returned)

    # Assert
    assert results[0].applied == 1


def test_a_returning_peer_does_not_resend_what_was_already_applied(local, make_store):
    """The cursor is what makes reconnection cheap AND idempotent."""
    # Arrange
    peer = make_store("peer")
    peer.put({"id": "p1"}, expected_revision=NEW_RECORD)
    sync(local, peer)

    # Act
    sync(local, peer)

    # Assert
    assert local.cursor("peer") == 1


def test_a_new_host_can_join_with_no_ceremony(local, make_store):
    """A host added later replays from zero. No registration, no handshake."""
    # Arrange
    for index in range(10):
        local.put({"id": f"c{index}"}, expected_revision=NEW_RECORD)
    newcomer = make_store("newcomer")

    # Act
    sync(newcomer, local)

    # Assert
    assert len(newcomer.rows()) == 10


def test_a_new_host_starts_with_an_empty_cursor_for_an_unknown_peer(local):
    """An unknown source reads as cursor 0 — 'nothing applied yet'.

    Not an error, and not a special case to configure: a peer nobody has
    heard of is simply one whose ops all still lie ahead.
    """
    # Arrange
    source = "a-host-that-has-never-been-seen"

    # Act
    cursor = local.cursor(source)

    # Assert
    assert cursor == 0


def test_a_dropped_hosts_rows_survive_its_departure(local, make_store):
    """Dropping a host does not remove what it contributed.

    The obvious wrong behaviour — "this host is gone, so remove its rows" —
    is the board-wipe inference wearing a different hat. It is unavailable
    here for the same reason: nothing can delete a row.
    """
    # Arrange
    departing = make_store("departing")
    departing.put({"id": "from-departing"}, expected_revision=NEW_RECORD)
    sync(local, departing)

    # Act
    departing.close()

    # Assert
    assert local.get({"id": "from-departing"}) is not None


def test_three_hosts_converge_on_the_same_row_count(local, make_store):
    """No coordinator: each pair syncs directly and all three agree."""
    # Arrange
    second = make_store("second")
    third = make_store("third")
    local.put({"id": "a"}, expected_revision=NEW_RECORD)
    second.put({"id": "b"}, expected_revision=NEW_RECORD)
    third.put({"id": "c"}, expected_revision=NEW_RECORD)

    # Act
    for target, sources in ((local, (second, third)), (second, (local, third)), (third, (local, second))):
        for source in sources:
            sync(target, source)

    # Assert
    assert [len(local.rows()), len(second.rows()), len(third.rows())] == [3, 3, 3]


def test_relayed_ops_keep_their_original_origin(local, make_store):
    """A relayed op belongs to whoever minted it, not to the relay.

    This is what lets hosts gossip through each other instead of needing a
    direct link to every peer — the third host's cursor for the first host
    stays meaningful even though the ops arrived via the second.
    """
    # Arrange
    second = make_store("second")
    third = make_store("third")
    local.put({"id": "from-local"}, expected_revision=NEW_RECORD)
    sync(second, local)

    # Act
    sync(third, second)

    # Assert
    assert third.cursor("local") == 1

# EOF
