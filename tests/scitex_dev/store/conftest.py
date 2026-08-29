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

THE DEFAULT DSN POINTS AT THE PRIMARY, AND THAT IS THE FIX, NOT A DETAIL.
It used to default to ``127.0.0.1:55432``, which on every host in this fleet
is a READ-ONLY REPLICA: ``CREATE SCHEMA`` raises there, the fixture skipped,
and the whole database-backed half of this suite reported green while
running nothing. Measured 2026-08-29 — the loopback answers
``pg_is_in_recovery() = true`` on every host. A replica is now a FAILURE
rather than a skip, because "no writable cluster" is a broken environment
and a suite that hides it is worse than one that stops.

Point elsewhere with ``SCITEX_TEST_PG_DSN``.
"""

from __future__ import annotations

import os
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
)

#: The cluster the suite builds its throwaway schemas on. The PRIMARY by
#: default: the per-host loopback is a standby and refuses DDL.
BASE_DSN = os.environ.get(
    "SCITEX_TEST_PG_DSN", "postgresql://scitex-primary:55432/scitex"
)


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
                f"{BASE_DSN} is a READ-ONLY STANDBY, so no test schema can be "
                "created and this suite would silently test nothing. Point "
                "SCITEX_TEST_PG_DSN at the primary."
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
