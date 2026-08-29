#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Both dialects answer the same questions, and answer them differently.

The dialect layer exists so a caller never learns which engine it is talking
to. That only holds if every dialect implements the WHOLE contract — a
missing method surfaces as an ``AttributeError`` deep inside a write, on
whichever host happens to run the other engine.

So these iterate over the registered dialects rather than naming one. A third
engine added later is covered the day it is registered, without anyone
remembering to extend this file.
"""

from __future__ import annotations

import pytest

from scitex_dev.store._dialect import Dialect, get_dialect, iter_dialects
from scitex_dev.store._policy import FieldKind
from scitex_dev.store._target import Backend


@pytest.fixture(params=list(iter_dialects()), ids=lambda backend: backend.value)
def dialect(request) -> Dialect:
    """Each registered dialect in turn — no engine is named here."""
    return get_dialect(request.param)


class TestEveryDialectImplementsTheWholeContract:
    """A partially implemented dialect fails deep inside a write, not here."""

    def test_placeholder_is_implemented(self, dialect):
        # Arrange
        index = 0
        # Act
        rendered = dialect.placeholder(index)
        # Assert
        assert rendered

    def test_quote_is_implemented(self, dialect):
        # Arrange
        identifier = "cards"
        # Act
        rendered = dialect.quote(identifier)
        # Assert
        assert rendered

    def test_every_field_kind_maps_to_a_column_type(self, dialect):
        """An unmapped kind would fail at CREATE TABLE on one engine only."""
        # Arrange
        kinds = list(FieldKind)
        # Act
        mapped = [dialect.column_type(kind) for kind in kinds]
        # Assert
        assert all(mapped)

    def test_upsert_sql_is_implemented(self, dialect):
        # Arrange
        columns = ["id", "title"]
        # Act
        statement = dialect.upsert_sql("cards", columns, "id")
        # Assert
        assert statement

    def test_a_boolean_round_trips_through_the_engine_representation(
        self, dialect
    ):
        """A driver may not have a boolean type; the round-trip must survive."""
        # Arrange
        original = True
        # Act
        restored = dialect.from_db_bool(dialect.to_db_bool(original))
        # Assert
        assert restored is True

    def test_a_false_boolean_round_trips_too(self, dialect):
        """The failing half of a bool conversion is usually False, not True."""
        # Arrange
        original = False
        # Act
        restored = dialect.from_db_bool(dialect.to_db_bool(original))
        # Assert
        assert restored is False


class TestQuotingIsAppliedRatherThanAssumed:
    """An unquoted identifier collides with a reserved word eventually."""

    def test_quote_changes_the_identifier(self, dialect):
        # Arrange
        identifier = "order"
        # Act
        quoted = dialect.quote(identifier)
        # Assert
        assert quoted != identifier

    def test_the_quoted_form_still_contains_the_identifier(self, dialect):
        # Arrange
        identifier = "order"
        # Act
        quoted = dialect.quote(identifier)
        # Assert
        assert identifier in quoted


class TestPlaceholdersAreEngineSpecific:
    """Placeholders come from the dialect, never from a caller's string."""

    def test_postgres_does_not_use_a_positional_question_mark(self):
        """The layer exists so no caller has to know which spelling it is."""
        # Arrange
        postgres = get_dialect(Backend.POSTGRES)
        # Act
        rendered = postgres.placeholder(0)
        # Assert
        assert rendered != "?"

    def test_placeholders_renders_one_per_column(self, dialect):
        # Arrange
        count = 3
        # Act
        rendered = dialect.placeholders(count)
        # Assert
        assert rendered.count(",") == count - 1


class TestTheEngineIsRegistered:
    """The registry is what makes 'iterate over dialects' meaningful."""

    def test_postgres_is_registered(self):
        # Arrange
        registered = list(iter_dialects())
        # Act
        present = Backend.POSTGRES in registered
        # Assert
        assert present


# EOF
