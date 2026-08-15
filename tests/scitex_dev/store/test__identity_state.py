#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the store-side plumbing behind ``Store.identity``.

The two halves are read from two different places, and that is the whole
design. ``store_uuid`` comes out of the store's own table, so it TRAVELS
with the data and every copy agrees on it. ``system_identifier`` is asked
of the serving system, so it does NOT travel and a copy disagrees with its
original.

Reading both from one place would produce a pair that is really one value
twice, and it would be exactly as blind to a fork as ``store_uuid`` alone —
which is the state the fleet was in on 2026-08-11.

Everything here runs against a real SQLite file. The device/inode pair is
the point: nothing but the filesystem can tell a file from a copy of it.
"""

from __future__ import annotations

import shutil

import pytest

from scitex_dev.store import NEW_RECORD, Store, StoreTarget, WriterPolicy


@pytest.fixture
def opened(tmp_path, card_schema):
    """A store on disk, holding one record."""
    store = Store(
        StoreTarget.sqlite(tmp_path / "one.db", pkg="cards"),
        card_schema,
        node="node-a",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )
    store.put({"id": "c0", "status": "open"}, expected_revision=NEW_RECORD)
    return store


@pytest.fixture
def sibling(tmp_path, card_schema):
    """A second, independently created store."""
    return Store(
        StoreTarget.sqlite(tmp_path / "two.db", pkg="cards"),
        card_schema,
        node="node-b",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )


def test_a_lineage_is_minted_on_first_read(opened):
    # Arrange — minting in __init__ would write to every store merely opened
    # for a read.
    # Act
    minted = opened.identity.store_uuid
    # Assert
    assert minted


def test_the_lineage_is_stable_across_reads(opened):
    # Arrange
    first = opened.identity.store_uuid
    # Act
    second = opened.identity.store_uuid
    # Assert
    assert second == first


def test_the_lineage_survives_reopening(opened, tmp_path, card_schema):
    # Arrange — it lives in the store's own table, which is what makes it
    # the LINEAGE rather than a property of the process.
    minted = opened.identity.store_uuid
    opened.close()
    # Act
    reopened = Store(
        StoreTarget.sqlite(tmp_path / "one.db", pkg="cards"),
        card_schema,
        node="node-a",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )
    # Assert
    assert reopened.identity.store_uuid == minted


def test_two_independent_stores_get_different_lineages(opened, sibling):
    # Arrange — the mint is a plain uuid4, deliberately NOT derived from the
    # path, the hostname or the time: a derived identity makes two stores on
    # similar-looking hosts collide, and a collision certifies two unrelated
    # stores as one.
    mine = opened.identity.store_uuid
    # Act
    theirs = sibling.identity.store_uuid
    # Assert
    assert theirs != mine


def test_the_instance_half_names_the_file(opened):
    # Arrange — SQLite has no cluster to ask, so the filesystem answers.
    # Act
    identifier = opened.identity.system_identifier
    # Assert
    assert identifier.startswith("sqlite:")


def test_the_instance_half_says_where_it_came_from(opened):
    # Arrange — two identities are only comparable when they were measured
    # the same way, and an operator reading a fork report needs to know what
    # the claim rests on.
    # Act
    source = opened.identity.system_source
    # Assert
    assert source == "file device/inode"


def test_a_copy_keeps_the_lineage(opened, tmp_path, card_schema):
    # Arrange — a uuid stored INSIDE a database cannot detect a fork of that
    # database, because the fork copies the uuid along with everything else.
    minted = opened.identity.store_uuid
    opened.close()
    shutil.copyfile(tmp_path / "one.db", tmp_path / "copy.db")
    # Act
    copied = Store(
        StoreTarget.sqlite(tmp_path / "copy.db", pkg="cards"),
        card_schema,
        node="node-a",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )
    # Assert
    assert copied.identity.store_uuid == minted


def test_a_copy_gets_a_different_instance(opened, tmp_path, card_schema):
    # Arrange — THE discriminator. `cp store.db store.db.bak` produces a new
    # inode, and that difference is what turns "same uuid" from a certificate
    # of sameness into a report of a FORK.
    mine = opened.identity.system_identifier
    opened.close()
    shutil.copyfile(tmp_path / "one.db", tmp_path / "copy.db")
    # Act
    copied = Store(
        StoreTarget.sqlite(tmp_path / "copy.db", pkg="cards"),
        card_schema,
        node="node-a",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )
    # Assert
    assert copied.identity.system_identifier != mine


def test_the_identity_reads_back_as_one_line(opened):
    # Arrange — it goes in logs, card notes and error messages.
    # Act
    line = opened.identity.describe()
    # Assert
    assert "on instance sqlite:" in line

# EOF
