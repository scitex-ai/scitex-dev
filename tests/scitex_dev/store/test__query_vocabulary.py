#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The half of the search surface that needs no database.

A :class:`~scitex_dev.store.Query` is a DESCRIPTION, and every check it
makes about a field — does the schema declare it, is this operator
meaningful for its kind — happens while the statement is being built. So
these run anywhere, and they are the tests that catch the failure the
engine cannot: a typo in a field name turning into an empty result set with
nothing to explain it.

The engine-side behaviour — ``NULLS LAST``, real JSON containment, the
full-text expression matching its own index — lives in
``test__query_search.py``, against a real PostgreSQL schema.
"""

from __future__ import annotations

import pytest

from scitex_dev.store import (
    Condition,
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    Op,
    Query,
    Schema,
    SchemaError,
    either,
    eq,
    gte,
    is_in,
    nonempty,
)


def _policy(
    kind: FieldKind,
    *,
    role=FieldRole.DATA,
    merge=MergeRule.LAST_WRITER_WINS,
    required: bool = False,
):
    return FieldPolicy(
        kind=kind, role=role, required=required, merge=merge, indexed=False
    )


def _identity() -> FieldPolicy:
    return _policy(
        FieldKind.TEXT,
        role=FieldRole.IDENTITY,
        merge=MergeRule.IMMUTABLE,
        required=True,
    )


def test_where_refuses_something_that_is_not_a_predicate():
    """A bare SQL string would be dropped, reading as a live filter."""
    # Arrange
    query = Query()
    # Act
    # Assert
    with pytest.raises(SchemaError, match="Condition or Either"):
        query.where("source = 'dandi'")


def test_limited_refuses_a_negative_limit():
    # Arrange
    query = Query()
    # Act
    # Assert
    with pytest.raises(SchemaError, match="must not be negative"):
        query.limited(-1)


def test_limited_refuses_a_negative_offset():
    # Arrange
    query = Query()
    # Act
    # Assert
    with pytest.raises(SchemaError, match="must not be negative"):
        query.limited(10, offset=-5)


def test_either_with_no_options_is_refused():
    """It can never hold, so it would empty every result set in silence."""
    # Arrange
    build = either
    # Act
    # Assert
    with pytest.raises(SchemaError, match="never hold"):
        build()


def test_a_valueless_operator_refuses_a_value():
    """A value that is ignored reads exactly like one that is applied."""
    # Arrange
    field_name = "readme"
    # Act
    # Assert
    with pytest.raises(SchemaError, match="takes no value"):
        Condition(field_name, Op.NONEMPTY, "x")


def test_is_in_refuses_a_bare_string():
    """A string is iterable, so this would silently become a character set."""
    # Arrange
    field_name = "source"
    # Act
    # Assert
    with pytest.raises(SchemaError, match="needs a collection"):
        is_in(field_name, "dandi")


def test_matching_blank_text_clears_the_criterion():
    """So an optional search box passes straight through without a branch."""
    # Arrange
    query = Query().matching("eeg")

    # Act
    cleared = query.matching("   ")

    # Assert
    assert cleared.text is None


def test_matching_none_clears_the_criterion():
    # Arrange
    query = Query().matching("eeg")

    # Act
    cleared = query.matching(None)

    # Assert
    assert cleared.text is None


def test_a_query_is_immutable_under_refinement():
    """Every builder returns a NEW query, so a shared base cannot be edited
    from under a caller that already holds it."""
    # Arrange
    base = Query()

    # Act
    base.where(eq("source", "dandi")).ordered_by("downloads").limited(5)

    # Assert
    assert base == Query()


def test_named_fields_reports_every_field_the_query_mentions():
    # Arrange
    query = Query().where(eq("source", "dandi"), gte("n_subjects", 5))

    # Act
    named = query.ordered_by("downloads").named_fields()

    # Assert
    assert set(named) == {"source", "n_subjects", "downloads"}


def test_named_fields_reaches_inside_a_disjunction():
    # Arrange
    query = Query().where(either(eq("a", 1), eq("b", 2)))

    # Act
    named = query.named_fields()

    # Assert
    assert set(named) == {"a", "b"}


def test_nonempty_builds_a_valueless_condition():
    # Arrange
    field_name = "readme"

    # Act
    condition = nonempty(field_name)

    # Assert
    assert condition.value is None


def test_text_search_naming_an_undeclared_field_is_refused():
    # Arrange
    fields = {"id": _identity()}
    # Act
    # Assert
    with pytest.raises(SchemaError, match="text_search names"):
        Schema.build("t", fields, text_search=("title",))


def test_text_search_naming_a_number_is_refused():
    """Casting a count to text so it can be searched makes every digit a
    term, and ``2020`` then matches a subject count as readily as a year."""
    # Arrange
    fields = {"id": _identity(), "n": _policy(FieldKind.INTEGER)}
    # Act
    # Assert
    with pytest.raises(SchemaError, match="neither TEXT nor JSON"):
        Schema.build("t", fields, text_search=("n",))


def test_text_search_accepts_a_json_field():
    """A JSON list of tags is exactly the kind of column worth searching."""
    # Arrange
    fields = {"id": _identity(), "tags": _policy(FieldKind.JSON)}

    # Act
    schema = Schema.build("t", fields, text_search=("tags",))

    # Assert
    assert schema.text_search == ("tags",)


def test_text_config_defaults_to_english():
    # Arrange
    fields = {"id": _identity(), "body": _policy(FieldKind.TEXT)}

    # Act
    schema = Schema.build("t", fields, text_search=("body",))

    # Assert
    assert schema.text_config == "english"


def test_text_config_refuses_a_value_that_is_not_an_identifier():
    """It is embedded in an index expression, not bound as a parameter."""
    # Arrange
    fields = {"id": _identity(), "body": _policy(FieldKind.TEXT)}
    # Act
    # Assert
    with pytest.raises(SchemaError, match="valid identifier"):
        Schema.build("t", fields, text_search=("body",), text_config="en'; DROP")


def test_a_schema_without_text_search_declares_none():
    """The default is not-searchable, so asking is an error rather than a
    quietly empty answer."""
    # Arrange
    fields = {"id": _identity(), "body": _policy(FieldKind.TEXT)}

    # Act
    schema = Schema.build("t", fields)

    # Assert
    assert schema.text_search == ()

# EOF
