#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for store-plugin discovery.

Every test here runs with BOTH seams closed — ``include_entry_points=False``
and ``include_builtins=False`` — unless it is specifically about one of
them. That is what licenses the exact-list assertions below: with the walk
left on, the result depends on which leaves happen to be installed in the
running environment, and an exact list would pass on the author's machine
and fail in CI, or the reverse.
"""

from __future__ import annotations

import pytest

from scitex_dev.store import (
    Schema,
    StoreError,
    StorePlugin,
    WriterPolicy,
    discover_store_plugins,
    plugin_for,
)
from scitex_dev.store.federation._discover import ENTRY_POINT_GROUP


def _declare(schema, *, name=None, pkg="cards", provider="scitex-cards"):
    """A provider callable declaring one store, optionally renamed."""
    if name is not None:
        schema = Schema.build(name, dict(schema.fields))
    plugin = StorePlugin(
        name=schema.name,
        pkg=pkg,
        schema=schema,
        writer_policy=WriterPolicy.MULTI_WRITER,
        provider=provider,
    )
    return lambda: [plugin]


def _isolated(**kwargs):
    """Discovery with both environment seams closed."""
    return discover_store_plugins(
        include_entry_points=False, include_builtins=False, **kwargs
    )


def test_entry_point_group_name_is_stable():
    # Arrange — PINNED. Renaming this orphans every installed leaf
    # SILENTLY: discovery would find nothing and report an empty
    # federation, which is indistinguishable from "no leaf has adopted the
    # store yet". sac and scitex-cards both declare against this string.
    expected = "scitex_dev.store.plugins"
    # Act
    got = ENTRY_POINT_GROUP
    # Assert
    assert got == expected


def test_both_seams_closed_yields_exactly_nothing():
    # Arrange — the isolation guarantee itself. If this ever returns a
    # non-empty list, every exact-list assertion in this file is measuring
    # the environment rather than the code.
    # Act
    found = _isolated()
    # Assert
    assert found == []


def test_an_extra_provider_is_aggregated(card_schema):
    # Arrange
    provider = _declare(card_schema)
    # Act
    found = _isolated(extra_providers=[provider])
    # Assert
    assert [p.name for p in found] == ["cards"]


def test_results_are_sorted_by_name(card_schema):
    # Arrange
    later = _declare(card_schema, name="zebra")
    earlier = _declare(card_schema, name="alpha")
    # Act
    found = _isolated(extra_providers=[later, earlier])
    # Assert
    assert [p.name for p in found] == ["alpha", "zebra"]


def test_a_duplicate_name_keeps_the_first_declaration(card_schema):
    # Arrange — only one package may own a store's merge semantics.
    first = _declare(card_schema, provider="scitex-cards")
    second = _declare(card_schema, provider="impostor", pkg="other")
    # Act
    found = _isolated(extra_providers=[first, second])
    # Assert
    assert [p.provider for p in found] == ["scitex-cards"]


def test_a_provider_that_raises_does_not_take_the_federation_down(card_schema):
    # Arrange — one leaf shipping a broken declaration must not stop every
    # other leaf's store from resolving.
    def broken():
        raise RuntimeError("this leaf is misconfigured")

    healthy = _declare(card_schema)
    # Act
    found = _isolated(extra_providers=[broken, healthy])
    # Assert
    assert [p.name for p in found] == ["cards"]


def test_a_provider_that_raises_is_logged(card_schema, caplog):
    # Arrange — skipped, but never SILENTLY: a swallowed provider error is
    # indistinguishable from a leaf that declares nothing.
    def broken():
        raise RuntimeError("this leaf is misconfigured")

    # Act
    with caplog.at_level("WARNING"):
        _isolated(extra_providers=[broken])
    # Assert
    assert "it raised" in caplog.text


def test_a_non_plugin_declaration_is_ignored(card_schema):
    # Arrange
    def wrong_shape():
        return ["cards"]

    healthy = _declare(card_schema)
    # Act
    found = _isolated(extra_providers=[wrong_shape, healthy])
    # Assert
    assert [p.name for p in found] == ["cards"]


def test_plugin_for_returns_the_declaring_plugin(card_schema):
    # Arrange
    provider = _declare(card_schema)
    # Act
    found = plugin_for(
        "cards",
        extra_providers=[provider],
        include_entry_points=False,
        include_builtins=False,
    )
    # Assert
    assert found.provider == "scitex-cards"


def test_an_empty_federation_says_it_is_empty():
    # Arrange — "no leaf has declared a store at all" and "that particular
    # store is not declared" have different causes (a missing install
    # versus a typo), so one message covering both would send the reader
    # looking in the wrong place.
    # Act
    # Assert
    with pytest.raises(StoreError, match="federation is EMPTY"):
        plugin_for("cards", include_entry_points=False, include_builtins=False)


def test_a_missing_store_names_the_ones_that_were_found(card_schema):
    # Arrange
    provider = _declare(card_schema)
    # Act
    # Assert
    with pytest.raises(StoreError, match=r"Declared stores: \['cards'\]"):
        plugin_for(
            "notes",
            extra_providers=[provider],
            include_entry_points=False,
            include_builtins=False,
        )

# EOF
