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

import atexit
import uuid
from contextlib import ExitStack
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
from scitex_dev.store.testing import writable_dsn

#: The cluster the suite builds its throwaway schemas on.
#:
#: THIS NAMES NO SERVER, AND THAT IS THE POINT. ``writable_dsn()`` tries the
#: configured store, then this host's, then starts a throwaway cluster — and
#: it VERIFIES writability rather than assuming it, so a standby is never
#: mistaken for a usable target. An earlier revision of this file hardcoded a
#: DSN literal and two sibling modules hardcoded their own: three copies of
#: one fact, each free to drift from the product.
#:
#: The stack is held open for the whole session and closed at exit, because a
#: throwaway cluster must outlive collection and every test that uses it.
_STACK = ExitStack()
atexit.register(_STACK.close)
BASE_DSN = _STACK.enter_context(writable_dsn())


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


# -- the search-surface fixtures ------------------------------------------
#
# Shared by `test__query_search.py` and `test__query_text.py`, which split
# the same catalogue two ways: what the FILTERS do, and what the FULL TEXT
# does. One set of records, declared once, so the two files cannot drift
# into disagreeing about what is in the store they are both asserting on.

#: Four records: two sources, one empty readme, one absent download count,
#: and one that the `catalog` fixture then hides.
CATALOG_RECORDS = (
    {
        "id": "openneuro:ds001",
        "source": "openneuro",
        "name": "Alzheimer memory study",
        "readme": "Resting state recordings of memory impairment.",
        "n_subjects": 30,
        "downloads": 500,
        "modalities": ["mri", "eeg"],
    },
    {
        "id": "openneuro:ds002",
        "source": "openneuro",
        "name": "Motor control",
        "readme": "",
        "n_subjects": 10,
        "downloads": 100,
        "modalities": ["mri"],
    },
    {
        "id": "dandi:000003",
        "source": "dandi",
        "name": "Hippocampal spiking",
        "readme": "Electrophysiology during a memory task.",
        "n_subjects": 50,
        "downloads": None,
        "modalities": ["ephys"],
    },
    {
        "id": "dandi:000004",
        "source": "dandi",
        "name": "Retired recording",
        "readme": "Withdrawn.",
        "n_subjects": 5,
        "downloads": 900,
        "modalities": [],
    },
)


def _catalog_policy(
    kind: FieldKind,
    *,
    role: FieldRole = FieldRole.DATA,
    merge: MergeRule = MergeRule.LAST_WRITER_WINS,
    required: bool = False,
) -> FieldPolicy:
    return FieldPolicy(
        kind=kind, role=role, required=required, merge=merge, indexed=False
    )


def catalog_fields() -> dict:
    """The catalogue's columns: text, numbers, a JSON list, a hide flag."""
    return {
        "id": _catalog_policy(
            FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            merge=MergeRule.IMMUTABLE,
            required=True,
        ),
        "source": _catalog_policy(FieldKind.TEXT),
        "name": _catalog_policy(FieldKind.TEXT),
        "readme": _catalog_policy(FieldKind.TEXT),
        "n_subjects": _catalog_policy(FieldKind.INTEGER),
        "downloads": _catalog_policy(FieldKind.INTEGER),
        "modalities": _catalog_policy(FieldKind.JSON),
        "hidden": _catalog_policy(FieldKind.BOOL, role=FieldRole.HIDE_FLAG),
    }


@pytest.fixture
def catalog_schema() -> Schema:
    """The catalogue with three of its columns declared searchable."""
    return Schema.build(
        "catalog",
        catalog_fields(),
        text_search=("name", "readme", "modalities"),
    )


@pytest.fixture
def open_store(pg_schemas):
    """Factory: a store on ``schema``, in a Postgres schema of its own.

    ``key`` names that Postgres schema. Two calls with the same key REOPEN
    one store — which is how a test asks whether a second open of an
    existing store behaves — while the default gives each call a fresh one.
    """

    def _make(schema: Schema, node: str, *, key: "str | None" = None) -> Store:
        name = pg_schemas(key or f"{node}_{uuid.uuid4().hex[:6]}")
        return Store(
            StoreTarget.postgres(
                f"{BASE_DSN}?options=-csearch_path%3D{name}", pkg="catalog"
            ),
            schema,
            node=node,
            writer_policy=WriterPolicy.MULTI_WRITER,
        )

    return _make


@pytest.fixture
def catalog(open_store, catalog_schema) -> Store:
    """A searchable catalogue holding :data:`CATALOG_RECORDS`, last hidden."""
    store = open_store(catalog_schema, "catalog")
    for record in CATALOG_RECORDS:
        store.put(record, expected_revision=NEW_RECORD)
    store.hide({"id": "dandi:000004"}, expected_revision=1)
    return store


@pytest.fixture
def unsearchable(open_store) -> Store:
    """The same shape with no ``text_search`` declaration."""
    return open_store(Schema.build("plain", catalog_fields()), "plain")

# EOF
