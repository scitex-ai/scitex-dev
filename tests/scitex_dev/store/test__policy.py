#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for FieldRole.DERIVED / MergeRule.RECOMPUTED.

The property under test is that **a computed field cannot be half-declared**.
``FieldRole.DERIVED`` and ``MergeRule.RECOMPUTED`` are two halves of one
statement -- "this value is computed, not written, and is rebuilt after a
merge" -- and a policy carrying only one half asserts two different things
about the same field.

That is worth a test in BOTH directions rather than one, because a check
written as a single implication passes one of the two bad declarations. The
role-without-rule case is the one an author is likely to write; the
rule-without-role case is the one a config file is likely to produce.

Why the role exists at all: a value derived from the whole TABLE (a rank, a
position) has no merge. Two isolated replicas each compute a valid ordering
over the rows they can see, and no combination preserves both, because the
two orderings answer a question about different sets. Left as
``LAST_WRITER_WINS`` the store would silently keep one replica's ordering of
the other replica's rows -- wrong as a whole, wrong in no single field, and
raising nothing.
"""

from __future__ import annotations

import pytest

from scitex_dev.store._errors import FieldPolicyError
from scitex_dev.store._policy import (
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    Schema,
)


def _kw(**over):
    """Valid kwargs for a DERIVED policy, overridable per test."""
    base = dict(
        kind=FieldKind.INTEGER,
        role=FieldRole.DERIVED,
        required=False,
        merge=MergeRule.RECOMPUTED,
        indexed=False,
    )
    base.update(over)
    return base


def _identity():
    return FieldPolicy(
        kind=FieldKind.TEXT,
        role=FieldRole.IDENTITY,
        required=True,
        merge=MergeRule.IMMUTABLE,
        indexed=True,
    )


# --- shape ---
def test_derived_with_recomputed_constructs():
    # Arrange
    kwargs = _kw()
    # Act
    policy = FieldPolicy(**kwargs)
    # Assert
    assert policy.role is FieldRole.DERIVED


def test_recomputed_is_a_merge_rule_member():
    # Arrange
    value = "recomputed"
    # Act
    act = MergeRule(value)
    # Assert
    assert act is MergeRule.RECOMPUTED


def test_derived_is_a_field_role_member():
    # Arrange
    value = "derived"
    # Act
    act = FieldRole(value)
    # Assert
    assert act is FieldRole.DERIVED


# --- the two halves must agree, in BOTH directions ---
def test_derived_role_without_recomputed_rule_is_refused():
    # Arrange
    kwargs = _kw(merge=MergeRule.LAST_WRITER_WINS)
    # Act
    act = lambda: FieldPolicy(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(FieldPolicyError, match="disagree"):
        act()


def test_recomputed_rule_without_derived_role_is_refused():
    # Arrange
    kwargs = _kw(role=FieldRole.DATA)
    # Act
    act = lambda: FieldPolicy(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(FieldPolicyError, match="disagree"):
        act()


def test_derived_field_may_not_be_required():
    # Arrange
    kwargs = _kw(required=True)
    # Act
    act = lambda: FieldPolicy(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(FieldPolicyError, match="required=False"):
        act()


# --- CONTROL ARM: the gate must be able to stay green ---
def test_ordinary_policies_are_unaffected():
    """A gate that fires on everything is not a gate.

    The new check sits on the same path every existing declaration takes, so
    this proves it does not reject the ordinary cases.
    """
    # Arrange
    kwargs = dict(
        kind=FieldKind.TEXT,
        role=FieldRole.DATA,
        required=False,
        merge=MergeRule.LAST_WRITER_WINS,
        indexed=False,
    )
    # Act
    policy = FieldPolicy(**kwargs)
    # Assert
    assert policy.merge is MergeRule.LAST_WRITER_WINS


# --- the schema view ---
def test_schema_reports_its_derived_fields():
    # Arrange
    schema = Schema.build(
        "t",
        {"id": _identity(), "row_order": FieldPolicy(**_kw())},
    )
    # Act
    act = schema.derived_fields
    # Assert
    assert act == ("row_order",)


def test_schema_without_derived_fields_reports_none():
    """CONTROL: the property must not simply return every field."""
    # Arrange
    schema = Schema.build("t", {"id": _identity()})
    # Act
    act = schema.derived_fields
    # Assert
    assert act == ()


def test_derived_field_is_not_an_identity_field():
    """A derived column must not silently become part of the record key."""
    # Arrange
    schema = Schema.build(
        "t",
        {"id": _identity(), "row_order": FieldPolicy(**_kw())},
    )
    # Act
    act = schema.identity_fields
    # Assert
    assert act == ("id",)


def test_from_mapping_accepts_the_new_values():
    """Config-shaped declarations reach the same policy as constructor ones."""
    # Arrange
    mapping = {
        "kind": "integer",
        "role": "derived",
        "required": False,
        "merge": "recomputed",
        "indexed": False,
    }
    # Act
    act = FieldPolicy.from_mapping("row_order", mapping)
    # Assert
    assert act == FieldPolicy(**_kw())
