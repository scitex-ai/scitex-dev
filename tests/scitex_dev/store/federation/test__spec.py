#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the StorePlugin contract.

Most cases here are a MALFORMED DECLARATION rejected at construction. That
is the point of validating in ``__post_init__`` rather than in discovery:
the traceback names the leaf that wrote the bad declaration, not whoever
happened to call ``discover_store_plugins`` an hour later.
"""

from __future__ import annotations

import pytest

from scitex_dev.store import StorePlugin, WriterPolicy


def _plugin(base_schema, **overrides) -> StorePlugin:
    """A valid declaration, with ``overrides`` swapped in."""
    kwargs = dict(
        name=base_schema.name,
        pkg="cards",
        schema=base_schema,
        writer_policy=WriterPolicy.MULTI_WRITER,
        provider="scitex-cards",
    )
    kwargs.update(overrides)
    return StorePlugin(**kwargs)


def test_a_valid_declaration_constructs(card_schema):
    # Arrange
    schema = card_schema
    # Act
    plugin = _plugin(schema)
    # Assert
    assert plugin.name == "cards"


def test_name_must_be_an_identifier(card_schema):
    # Arrange
    schema = card_schema
    # Act
    # Assert
    with pytest.raises(ValueError, match="valid identifier"):
        _plugin(schema, name="not a name")


def test_empty_pkg_is_refused(card_schema):
    # Arrange
    schema = card_schema
    # Act
    # Assert
    with pytest.raises(ValueError, match="package short name"):
        _plugin(schema, pkg="")


def test_schema_must_be_a_schema(card_schema):
    # Arrange
    schema = card_schema
    # Act
    # Assert
    with pytest.raises(ValueError, match=r"Schema\.build\(\)"):
        _plugin(schema, schema="cards")


def test_schema_name_must_match_plugin_name(card_schema):
    # Arrange — the schema name is the TABLE PREFIX and the plugin name is
    # how the federation refers to the store; a mismatch would have
    # discovery and the database disagree about which store is which.
    schema = card_schema
    # Act
    # Assert
    with pytest.raises(ValueError, match="They must agree"):
        _plugin(schema, name="notcards")


def test_writer_policy_must_be_a_writer_policy(card_schema):
    # Arrange
    schema = card_schema
    # Act
    # Assert
    with pytest.raises(ValueError, match="must be a WriterPolicy"):
        _plugin(schema, writer_policy="multi")


def test_empty_provider_is_refused(card_schema):
    # Arrange
    schema = card_schema
    # Act
    # Assert
    with pytest.raises(ValueError, match="declaring package"):
        _plugin(schema, provider="  ")


def test_describe_names_the_declaring_package(card_schema):
    # Arrange
    plugin = _plugin(card_schema)
    # Act
    line = plugin.describe()
    # Assert
    assert "[scitex-cards]" in line

# EOF
