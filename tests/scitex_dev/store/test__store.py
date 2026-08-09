#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression suite for the board-wipe class.

Named after the ruling it enforces, not after the postmortem:

    "No code may delete a row because it is absent from another store."
    -- scitex-cards, ADR-0016

The incident was THREE board wipes on 2026-07-19/21, one of which replaced
2,159 live rows with a 5-row temporary document. (2026-07-30 is the ADR's
date, not the event's. Searching for 07-30 finds the analysis and misses
the wipes — which is why the dates are spelled out here.)

scitex-cards identified three distinct doors onto one mechanism, and each
gets its own tests:

1. PEER-STORE door — two stores reconciled as peers, absence in one read as
   deletion in the other. This is the 2,159.
2. SECTION door — a sync that deletes a whole section when its hash differs
   and re-inserts from the incoming document, where the reader returns
   early without raising if the section is absent. Every count a reviewer
   would think to check stays green while the data is gone.
3. EMPTY-DOCUMENT door — a mirror diffing an outgoing document against the
   table on every ordinary write. Measured: five sequential writes each
   left exactly one row; on the live board, 2,065 cards down to 1.

What these prove is not that this primitive passes. It is that it cannot
express the failure: with no delete verb, a wrong reconciliation can
produce a wrong VALUE but never a missing ROW.
"""

from __future__ import annotations

from scitex_dev.store import NEW_RECORD, Store, sync


def _fill(store: Store, count: int, prefix: str = "c") -> None:
    for index in range(count):
        store.put(
            {"id": f"{prefix}{index}", "status": "open"},
            expected_revision=NEW_RECORD,
        )


# -- door 1: the peer-store door (the 2,159) ------------------------------
def test_syncing_from_a_smaller_peer_keeps_every_local_row(local, peer):
    """The 2,159 shape: a one-row peer must not reduce a 2,159-row store."""
    # Arrange
    _fill(local, 2159)
    peer.put({"id": "temp", "status": "scratch"}, expected_revision=NEW_RECORD)

    # Act
    sync(local, peer)

    # Assert
    assert len(local.rows()) == 2160


def test_syncing_from_a_smaller_peer_keeps_the_first_local_row(local, peer):
    """Spot-check an edge of the set rather than trusting the count."""
    # Arrange
    _fill(local, 2159)
    peer.put({"id": "temp", "status": "scratch"}, expected_revision=NEW_RECORD)

    # Act
    sync(local, peer)

    # Assert
    assert local.get({"id": "c0"}) is not None


def test_syncing_from_a_smaller_peer_keeps_the_last_local_row(local, peer):
    """The other edge. The middle is where a wipe is least likely to show."""
    # Arrange
    _fill(local, 2159)
    peer.put({"id": "temp", "status": "scratch"}, expected_revision=NEW_RECORD)

    # Act
    sync(local, peer)

    # Assert
    assert local.get({"id": "c2158"}) is not None


def test_syncing_from_a_smaller_peer_adopts_the_peers_row(local, peer):
    """Replay must still DO something — a no-op would pass the tests above."""
    # Arrange
    _fill(local, 10)
    peer.put({"id": "temp", "status": "scratch"}, expected_revision=NEW_RECORD)

    # Act
    sync(local, peer)

    # Assert
    assert local.get({"id": "temp"}) is not None


def test_syncing_from_an_empty_peer_removes_nothing(populated, peer):
    """The degenerate case: an empty peer must not mean 'delete everything'."""
    # Arrange
    expected = len(populated.rows())

    # Act
    sync(populated, peer)

    # Assert
    assert len(populated.rows()) == expected


def test_syncing_from_an_empty_peer_applies_no_batches(populated, peer):
    """An empty peer yields no work at all, rather than a destructive batch."""
    # Arrange
    _ = populated

    # Act
    results = sync(populated, peer)

    # Assert
    assert results == []


# -- door 2: the section door ---------------------------------------------
def test_a_peer_writing_only_one_section_keeps_the_other_section(local, peer):
    """A document with every card and no users must not erase the users.

    "Sections" here are records of different kinds in one store. Replay
    cannot touch a record no op names, so a peer that only ever writes
    cards has no way to affect users — whether or not it knows they exist.
    """
    # Arrange
    _fill(local, 20, prefix="card-")
    for name in ("alice", "bob", "carol"):
        local.put({"id": f"user-{name}", "status": "active"}, expected_revision=NEW_RECORD)
    _fill(peer, 20, prefix="card-")

    # Act
    sync(local, peer)

    # Assert
    assert len([r for r in local.rows() if str(r.values["id"]).startswith("user-")]) == 3


def test_a_peer_writing_only_one_section_keeps_the_total_row_count(local, peer):
    """The count stays right too — but the count alone would not prove it."""
    # Arrange
    _fill(local, 20, prefix="card-")
    for name in ("alice", "bob", "carol"):
        local.put({"id": f"user-{name}", "status": "active"}, expected_revision=NEW_RECORD)
    _fill(peer, 20, prefix="card-")

    # Act
    sync(local, peer)

    # Assert
    assert len(local.rows()) == 23


# -- door 3: the empty-document door --------------------------------------
def test_writing_one_new_record_leaves_every_other_record_present(populated):
    """A single-record write must not prune rows it never mentioned.

    The measured failure was five sequential writes each leaving one row.
    A per-record write door carries no statement about any other record.
    """
    # Arrange
    before = len(populated.rows())

    # Act
    populated.put({"id": "brand-new", "status": "open"}, expected_revision=NEW_RECORD)

    # Assert
    assert len(populated.rows()) == before + 1


def test_five_sequential_writes_leave_all_rows_present(populated):
    """The exact measured shape: five writes, nothing pruned between them."""
    # Arrange
    before = len(populated.rows())

    # Act
    for index in range(5):
        populated.put({"id": f"new-{index}"}, expected_revision=NEW_RECORD)

    # Assert
    assert len(populated.rows()) == before + 5


def test_updating_a_record_leaves_the_other_records_present(populated):
    """An update is a partial write, not a document replacement."""
    # Arrange
    before = len(populated.rows())

    # Act
    populated.put(
        {"id": "c0", "status": "closed"},
        expected_revision=populated.revision({"id": "c0"}),
    )

    # Assert
    assert len(populated.rows()) == before


# -- the API-level barrier ------------------------------------------------
def test_the_store_class_exposes_no_delete_shaped_method():
    """The absence of a delete verb is part of the contract, so assert it."""
    # Arrange
    words = ("delete", "remove", "drop", "purge")

    # Act
    found = [n for n in dir(Store) if any(w in n.lower() for w in words)]

    # Assert
    assert found == []

# EOF
