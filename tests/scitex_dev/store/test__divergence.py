#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for divergence detection.

The property under test throughout is that **absence is never evidence**.
Set-difference reconciliation replaced 2,159 live rows with a 5-row
document on 2026-07-19/21 by reading "present here, missing there" as a
deletion. A peer that is merely BEHIND has no op at the sequence in
question, so there is nothing to disagree with and nothing is reported.
"""

from __future__ import annotations

import shutil

import pytest

from scitex_dev.store import (
    NEW_RECORD,
    IdentityVerdict,
    Store,
    StoreDivergedError,
    StoreTarget,
    WriterPolicy,
    detect_divergence,
)


@pytest.fixture
def origin(tmp_path, card_schema):
    """A store with three ops, whose lineage uuid has been minted."""
    store = Store(
        StoreTarget.sqlite(tmp_path / "origin.db", pkg="cards"),
        card_schema,
        node="node-a",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )
    for index in range(3):
        store.put({"id": f"c{index}", "status": "open"}, expected_revision=NEW_RECORD)
    store.identity  # mint the lineage so the copy below inherits it
    return store


@pytest.fixture
def copied(origin, tmp_path, card_schema):
    """A byte-for-byte COPY of ``origin`` — same lineage, new instance."""
    origin.close()
    shutil.copyfile(tmp_path / "origin.db", tmp_path / "copy.db")
    return Store(
        StoreTarget.sqlite(tmp_path / "copy.db", pkg="cards"),
        card_schema,
        node="node-a",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )


@pytest.fixture
def reopened(origin, tmp_path, card_schema):
    """``origin`` re-opened after the copy was taken."""
    return Store(
        StoreTarget.sqlite(tmp_path / "origin.db", pkg="cards"),
        card_schema,
        node="node-a",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )


def test_a_copy_shares_its_originals_lineage(copied, reopened):
    # Arrange — a uuid stored INSIDE a database cannot detect a fork of that
    # database, because the fork copies the uuid along with everything else.
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.local_identity.store_uuid == report.remote_identity.store_uuid


def test_a_copy_is_a_different_instance(copied, reopened):
    # Arrange — `cp store.db store.db.bak` produces a new inode, and the
    # filesystem is the only thing that can tell a file from a copy of it.
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.identity_verdict is IdentityVerdict.FORK


def test_a_copy_is_reported_as_diverged(copied, reopened):
    # Arrange
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.diverged is True


def test_a_copy_is_not_certified_same(copied, reopened):
    # Arrange
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.certified_same is False


def test_an_untouched_copy_has_no_fork_point(copied, reopened):
    # Arrange — identity catches this fork BEFORE any divergence exists.
    # The log cannot: neither side has written since the split, so no
    # position was filled differently and nothing is PROVEN at the log level.
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.forks == ()


def test_a_peer_that_is_merely_behind_has_no_fork_point(copied, reopened):
    # Arrange — THE central claim. `reopened` runs ahead; `copied` simply
    # has no op at those sequences. Being behind is what a cursor is for.
    reopened.put({"id": "c9", "status": "open"}, expected_revision=NEW_RECORD)
    reopened.put({"id": "c10", "status": "open"}, expected_revision=NEW_RECORD)
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.forks == ()


def test_lag_is_reported_as_a_number_not_as_damage(peer, populated):
    # Arrange — `peer` has replayed nothing of `populated`'s fifty ops. It
    # is as far behind as a peer can be, and that is ORDINARY: it is what a
    # cursor is for.
    # Act
    report = detect_divergence(peer, populated)
    # Assert
    assert report.behind == {"local": 50}


def test_a_peer_that_has_nothing_yet_is_not_diverged(peer, populated):
    # Arrange — the inference this whole module exists to make unavailable:
    # "present here, missing there" is NOT a deletion, and fifty missing ops
    # are not damage.
    # Act
    report = detect_divergence(peer, populated)
    # Assert
    assert report.forks == ()


def test_two_writers_numbering_as_one_origin_are_proven_forked(copied, reopened):
    # Arrange — both halves mint seq 4 as node-a, with DIFFERENT content.
    # One origin cannot legitimately produce two different ops at one
    # sequence, so this is proof rather than inference.
    reopened.put({"id": "c3", "status": "open"}, expected_revision=NEW_RECORD)
    copied.put({"id": "c3", "status": "cancelled"}, expected_revision=NEW_RECORD)
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert [f.seq for f in report.forks] == [4]


def test_the_fork_point_names_the_origin_that_was_duplicated(copied, reopened):
    # Arrange
    reopened.put({"id": "c3", "status": "open"}, expected_revision=NEW_RECORD)
    copied.put({"id": "c3", "status": "cancelled"}, expected_revision=NEW_RECORD)
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.forks[0].origin == "node-a"


def test_the_earliest_disagreement_is_the_one_reported(copied, reopened):
    # Arrange — ops are immutable once written, so a fork produces an
    # agreeing PREFIX and then permanent disagreement. Agreement is monotone
    # in seq, which is what licenses the bisection.
    for index in range(3, 8):
        reopened.put({"id": f"c{index}", "status": "open"}, expected_revision=NEW_RECORD)
        copied.put({"id": f"c{index}", "status": "cancelled"}, expected_revision=NEW_RECORD)
    # Act
    report = detect_divergence(reopened, copied)
    # Assert
    assert report.forks[0].seq == 4


def test_raise_if_diverged_is_loud(copied, reopened):
    # Arrange — every failure of 2026-08-11 was silent because every call
    # reported success. This is the half that stops a caller.
    reopened.put({"id": "c3", "status": "open"}, expected_revision=NEW_RECORD)
    copied.put({"id": "c3", "status": "cancelled"}, expected_revision=NEW_RECORD)
    report = detect_divergence(reopened, copied)
    # Act
    # Assert
    with pytest.raises(StoreDivergedError, match="DIVERGED"):
        report.raise_if_diverged()


def test_raise_if_diverged_carries_the_callers_context(copied, reopened):
    # Arrange
    reopened.put({"id": "c3", "status": "open"}, expected_revision=NEW_RECORD)
    copied.put({"id": "c3", "status": "cancelled"}, expected_revision=NEW_RECORD)
    report = detect_divergence(reopened, copied)
    # Act
    # Assert
    with pytest.raises(StoreDivergedError, match="acking n-83"):
        report.raise_if_diverged(context="acking n-83")


def test_raise_if_diverged_stays_quiet_when_only_behind(peer, populated):
    # Arrange — lag must never raise. A healthy, catching-up peer that
    # looked corrupted is the mistake this module refuses to make.
    report = detect_divergence(peer, populated)
    # Act
    result = report.raise_if_diverged()
    # Assert
    assert result is None


def test_describe_names_both_sides(copied, reopened):
    # Arrange — short enough to put in a log line or a card note.
    report = detect_divergence(reopened, copied)
    # Act
    line = report.describe()
    # Assert
    assert "node-a vs node-a" in line

# EOF
