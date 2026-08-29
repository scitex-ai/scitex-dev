#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared fixtures for the store suite.

The suite keeps one assertion per test, so setup that would otherwise be
repeated in thirty functions lives here instead.

EVERY STORE HERE IS A REAL POSTGRES SCHEMA. There is one storage engine, so
there is no zero-setup engine to build a store on inside ``tmp_path``. Each
node gets its own schema on the cluster, created before the test and dropped
after, which keeps the isolation the old per-file stores had while testing
the engine that actually ships.

THE SUITE NAMES NO SERVER, AND THAT IS THE FIX, NOT A DETAIL. It used to
carry a DSN literal, and so did two sibling modules — three copies of one
fact. Worse, the literal they carried was ``127.0.0.1:55432``, which on every
host in this fleet is a READ-ONLY STANDBY: ``CREATE SCHEMA`` raises there,
the fixture skipped, and the whole database-backed half of this suite
reported green while running nothing. Measured 2026-08-29 — the loopback
answers ``pg_is_in_recovery() = true`` on every host.

Both halves are now fixed by the same move. The DSN comes from
``host_store()``, the single resolver the product itself uses, so there is
nothing here to drift. And a standby is a FAILURE rather than a skip, because
"no writable cluster" is a broken environment and a suite that hides that is
worse than one that stops.

Point elsewhere with ``SCITEX_STORE_DSN`` -- the single switch.
"""

from __future__ import annotations

import uuid
from typing import Iterator

import pytest

from scitex_dev.store import (
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    NEW_RECORD,
    Schema,
    Store,
    StoreTarget,
    WriterPolicy,
    host_store,
)

#: The cluster the suite builds its throwaway schemas on.
#:
#: THIS IS NOT A CONSTANT, AND THAT IS THE POINT. It asks the package's own
#: resolver, so exactly ONE thing in the world decides which PostgreSQL
#: anything talks to: ``host_store()``, which reads ``SCITEX_STORE_DSN`` and
#: otherwise falls back to this host's socket. An earlier revision of this
#: file hardcoded a DSN literal and two sibling test modules hardcoded their
#: own -- three copies of one fact, each free to drift from the product. A
#: test that names its own server is not testing the resolver the product
#: uses; it is testing a string.
BASE_DSN = host_store(pkg="scitex_dev_tests", name="probe").dsn


@pytest.fixture
def card_schema() -> Schema:
    """A minimal card-like schema: identity, a status, and a hide flag."""
    return Schema.build(
        "cards",
        {
            "id": FieldPolicy(
                kind=FieldKind.TEXT,
                role=FieldRole.IDENTITY,
                required=True,
                merge=MergeRule.IMMUTABLE,
                indexed=False,
            ),
            "status": FieldPolicy(
                kind=FieldKind.TEXT,
                role=FieldRole.DATA,
                required=False,
                merge=MergeRule.LAST_WRITER_WINS,
                indexed=True,
            ),
            "hidden": FieldPolicy(
                kind=FieldKind.BOOL,
                role=FieldRole.HIDE_FLAG,
                required=False,
                merge=MergeRule.LAST_WRITER_WINS,
                indexed=False,
            ),
        },
    )


@pytest.fixture
def pg_schemas() -> Iterator:
    """Factory for throwaway schemas on the cluster, dropped on teardown.

    A missing driver still SKIPS — that is a property of the interpreter, not
    of the store. An unreachable or read-only cluster FAILS: see the module
    docstring for why that distinction is the point of this fixture.
    """
    psycopg = pytest.importorskip("psycopg")
    prefix = f"test_store_{uuid.uuid4().hex[:10]}"
    created: list[str] = []

    with psycopg.connect(BASE_DSN, connect_timeout=5, autocommit=True) as probe:
        if probe.execute("SELECT pg_is_in_recovery()").fetchone()[0]:
            raise AssertionError(
                f"{BASE_DSN} is a READ-ONLY STANDBY, so no test schema can "
                "be created and this suite would silently test nothing. Set "
                "SCITEX_STORE_DSN to a writable cluster: it is the one switch, "
                "and host_store() is the only thing that reads it."
            )

    def _make(node: str) -> str:
        # ONE SCHEMA PER NODE NAME, and asking twice REOPENS rather than
        # collides. That is the semantics the suite is written against: the
        # replication tests close a peer and call make_store("peer") again to
        # model a peer coming BACK, and the returning store has to be the
        # same store or its cursor means nothing. Creating a second schema
        # there silently turned "a peer reconnects" into "a stranger appears"
        # and the cursor test failed for a reason that had nothing to do with
        # cursors.
        name = f"{prefix}_{node}"
        if name not in created:
            with psycopg.connect(BASE_DSN, connect_timeout=5, autocommit=True) as conn:
                conn.execute(f'CREATE SCHEMA "{name}"')
            created.append(name)
        return name

    try:
        yield _make
    finally:
        with psycopg.connect(BASE_DSN, connect_timeout=5, autocommit=True) as conn:
            for name in created:
                conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


@pytest.fixture
def make_store(pg_schemas, card_schema):
    """Factory: an independent store per node name, one schema each."""

    def _make(node: str, *, policy: WriterPolicy = WriterPolicy.MULTI_WRITER) -> Store:
        schema_name = pg_schemas(node)
        dsn = f"{BASE_DSN}?options=-csearch_path%3D{schema_name}"
        return Store(
            StoreTarget.postgres(dsn, pkg="cards"),
            card_schema,
            node=node,
            writer_policy=policy,
        )

    return _make


@pytest.fixture
def local(make_store) -> Store:
    """The store under test."""
    return make_store("local")


@pytest.fixture
def peer(make_store) -> Store:
    """A second, independent store to reconcile against."""
    return make_store("peer")


@pytest.fixture
def populated(local) -> Store:
    """``local`` holding fifty ordinary records."""
    for index in range(50):
        local.put({"id": f"c{index}", "status": "open"}, expected_revision=NEW_RECORD)
    return local

# EOF
