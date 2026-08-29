#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``Store.identity`` — the lineage is minted, the instance is asked.

Everything here runs against a real PostgreSQL schema. The identity has two
halves and they are established in genuinely different ways, which is the
whole design:

* ``store_uuid`` is MINTED once and lives in the store's own table, so it
  travels with the data. That is what makes it a LINEAGE.
* ``system_identifier`` is ASKED OF THE SERVING SYSTEM at connect time and is
  never read back from the rows. A value carried inside the data is copied
  with the data; a value asked of the machine is not.

TWO TESTS THAT USED TO LIVE HERE ARE GONE, DELIBERATELY. They copied a store
file byte-for-byte and asserted the copy kept the lineage while getting a new
instance id, because the instance half was the file's ``device:inode``. There
is no store file any more. The behaviour they protected — that the instance
id distinguishes two databases on ONE cluster, which is what a restored dump
produces — is asserted in ``_dialect/test__postgres.py`` against the
identifier SQL itself, and that test needs no live cluster. Porting these two
would have meant creating a second DATABASE, which the test role cannot do
(``rolcreatedb`` is false, measured 2026-08-29); a test that silently skipped
on that would be worse than one that is honestly absent.
"""

from __future__ import annotations

import pytest

from scitex_dev.store import NEW_RECORD, Store, StoreTarget, WriterPolicy

from .conftest import BASE_DSN


def _open(schema_name: str, card_schema, node: str) -> Store:
    dsn = f"{BASE_DSN}?options=-csearch_path%3D{schema_name}"
    return Store(
        StoreTarget.postgres(dsn, pkg="cards"),
        card_schema,
        node=node,
        writer_policy=WriterPolicy.MULTI_WRITER,
    )


@pytest.fixture
def one_schema(pg_schemas) -> str:
    """A schema of its own, reusable so a store can be reopened on it."""
    return pg_schemas("one")


@pytest.fixture
def opened(one_schema, card_schema) -> Store:
    """A store holding one record."""
    store = _open(one_schema, card_schema, "node-a")
    store.put({"id": "c0", "status": "open"}, expected_revision=NEW_RECORD)
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def sibling(pg_schemas, card_schema) -> Store:
    """A second, independently created store."""
    store = _open(pg_schemas("two"), card_schema, "node-b")
    try:
        yield store
    finally:
        store.close()


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


def test_the_lineage_survives_reopening(opened, one_schema, card_schema):
    # Arrange — it lives in the store's own table, which is what makes it
    # the LINEAGE rather than a property of the process.
    minted = opened.identity.store_uuid
    opened.close()
    # Act
    reopened = _open(one_schema, card_schema, "node-a")
    # Assert
    assert reopened.identity.store_uuid == minted


def test_two_independent_stores_get_different_lineages(opened, sibling):
    # Arrange — the mint is a plain uuid4, deliberately NOT derived from the
    # DSN, the hostname or the time: a derived identity makes two stores on
    # similar-looking hosts collide, and a collision certifies two unrelated
    # stores as one.
    mine = opened.identity.store_uuid
    # Act
    theirs = sibling.identity.store_uuid
    # Assert
    assert theirs != mine


def test_the_instance_half_names_the_cluster_and_database(opened):
    # Arrange — the cluster id alone is too coarse: a dump restored into a
    # second database on the SAME cluster shares it.
    # Act
    identifier = opened.identity.system_identifier
    # Assert
    assert identifier.startswith("pg:")


def test_the_instance_half_says_where_it_came_from(opened):
    # Arrange — two identities are only comparable when they were measured
    # the same way, and an operator reading a fork report needs to know what
    # the claim rests on.
    # Act
    source = opened.identity.system_source
    # Assert
    assert source == "pg_control_system() + current_database()"


def test_the_identity_reads_back_as_one_line(opened):
    # Arrange — it goes in logs, card notes and error messages.
    # Act
    line = opened.identity.describe()
    # Assert
    assert "on instance pg:" in line

# EOF
