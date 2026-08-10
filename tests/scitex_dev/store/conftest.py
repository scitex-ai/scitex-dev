#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared fixtures for the store suite.

The suite keeps one assertion per test, so setup that would otherwise be
repeated in thirty functions lives here instead.
"""

from __future__ import annotations

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
def make_store(tmp_path, card_schema):
    """Factory: an independent store per node name, all in one tmp dir."""

    def _make(node: str, *, policy: WriterPolicy = WriterPolicy.MULTI_WRITER) -> Store:
        return Store(
            StoreTarget.sqlite(tmp_path / f"{node}.db", pkg="cards"),
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
