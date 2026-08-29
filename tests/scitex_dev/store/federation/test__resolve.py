#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for turning a declaration into a target.

**A leaf does not resolve its own store target.** That is what these check:
that the pkg and the store name reaching
:func:`~scitex_dev.store._host.host_store` come from the DECLARATION rather
than from the caller.

Per-consumer resolution is what produced the 2026-08-11 split — two
processes on one host each resolved the card store their own way, one to the
host's Postgres and one through a tunnel to the NAS's, and both were
"correct" by their own configuration.

These drive the real ``SCITEX_STORE_DSN`` override through the real process
environment. It is a documented resolution step and returns without
connecting to anything, so nothing here is faked.
"""

from __future__ import annotations

import os

import pytest

from scitex_dev.store import (
    Backend,
    StorePlugin,
    StoreTargetError,
    WriterPolicy,
    resolve_target,
)
from scitex_dev.store._host import STORE_DSN_ENV

DSN = "postgresql://scitex@127.0.0.1:55432/scitex"


@pytest.fixture
def store_dsn():
    """Set the real override variable for one test; restore it afterwards."""
    previous = os.environ.get(STORE_DSN_ENV)

    def _set(value: str) -> None:
        os.environ[STORE_DSN_ENV] = value

    yield _set
    if previous is None:
        os.environ.pop(STORE_DSN_ENV, None)
    else:
        os.environ[STORE_DSN_ENV] = previous


@pytest.fixture
def plugin(card_schema) -> StorePlugin:
    """A leaf's declaration of the card store."""
    return StorePlugin(
        name=card_schema.name,
        pkg="cards",
        schema=card_schema,
        writer_policy=WriterPolicy.MULTI_WRITER,
        provider="scitex-cards",
    )


def test_the_target_carries_the_declared_package(plugin, store_dsn):
    # Arrange
    store_dsn(DSN)
    # Act
    target = resolve_target(plugin)
    # Assert
    assert target.pkg == "cards"


def test_the_target_carries_the_declared_store_name(plugin, store_dsn):
    # Arrange — the store name prefixes the table names, so a leaf declaring
    # `cards` must not end up writing to a table called `store`.
    store_dsn(DSN)
    # Act
    target = resolve_target(plugin)
    # Assert
    assert target.name == "cards"


def test_an_explicit_override_resolves_to_postgres(plugin, store_dsn):
    # Arrange
    store_dsn(DSN)
    # Act
    target = resolve_target(plugin)
    # Assert
    assert target.backend is Backend.POSTGRES


def test_a_path_in_the_override_is_refused_rather_than_downgraded(plugin, store_dsn):
    # Arrange — there is deliberately NO second tier. A host that
    # quietly started writing to a private local file would accept every
    # write, report success, and diverge from the fleet with nothing in any
    # log to say so.
    store_dsn("/home/me/.scitex/cards.db")
    # Act
    # Assert
    with pytest.raises(StoreTargetError, match="not a Postgres DSN"):
        resolve_target(plugin)

# EOF
