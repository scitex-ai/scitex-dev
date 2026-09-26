#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Declared package fields evolve deployed PostgreSQL stores safely."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from scitex_dev.store import (
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    NEW_RECORD,
    Schema,
    SchemaEvolutionError,
    Store,
    StoreTarget,
    WriterPolicy,
)

from .conftest import BASE_DSN


def _field(
    kind: FieldKind,
    *,
    role: FieldRole = FieldRole.DATA,
    required: bool = False,
    merge: MergeRule = MergeRule.LAST_WRITER_WINS,
) -> FieldPolicy:
    return FieldPolicy(
        kind=kind,
        role=role,
        required=required,
        merge=merge,
        indexed=False,
    )


def _schema(fields: dict[str, FieldPolicy]) -> Schema:
    return Schema.build(
        "evolution",
        {
            "id": _field(
                FieldKind.TEXT,
                role=FieldRole.IDENTITY,
                required=True,
                merge=MergeRule.IMMUTABLE,
            ),
            **fields,
        },
    )


def _target(pg_schemas, node: str = "evolution") -> StoreTarget:
    namespace = pg_schemas(node)
    dsn = f"{BASE_DSN}?options=-csearch_path%3D{namespace}"
    return StoreTarget.postgres(dsn, pkg="evolution")


def _open(target: StoreTarget, schema: Schema, node: str = "node") -> Store:
    return Store(
        target,
        schema,
        node=node,
        writer_policy=WriterPolicy.MULTI_WRITER,
    )


def test_open_adds_a_new_optional_data_field_and_preserves_old_rows(pg_schemas) -> None:
    # Arrange
    target = _target(pg_schemas)
    old = _open(target, _schema({"status": _field(FieldKind.TEXT)}))
    old.put({"id": "one", "status": "ready"}, expected_revision=NEW_RECORD)
    old.close()

    # Act
    current = _open(
        target,
        _schema(
            {
                "status": _field(FieldKind.TEXT),
                "process_uid": _field(FieldKind.INTEGER),
            }
        ),
    )
    try:
        # Assert
        assert current.get({"id": "one"}).values["process_uid"] is None
    finally:
        current.close()


def test_construction_reports_the_physically_added_declared_field(
    pg_schemas,
) -> None:
    # Arrange
    target = _target(pg_schemas)
    old = _open(target, _schema({"status": _field(FieldKind.TEXT)}))
    old.close()

    # Act
    current = _open(
        target,
        _schema(
            {
                "status": _field(FieldKind.TEXT),
                "scope_unit": _field(FieldKind.TEXT),
            }
        ),
    )
    try:
        # Assert
        assert current.schema_evolution.added == ("scope_unit",)
    finally:
        current.close()


def test_explicit_gate_is_idempotent_and_physically_observed(pg_schemas) -> None:
    # Arrange
    target = _target(pg_schemas)
    schema = _schema({"scope_unit": _field(FieldKind.TEXT)})
    store = _open(target, schema)
    try:
        # Act
        result = store.ensure_declared_fields()
        # Assert
        assert (result.added, result.existing, result.observed) == (
            (),
            ("id", "scope_unit"),
            ("id", "scope_unit"),
        )
    finally:
        store.close()


@pytest.mark.parametrize(
    "unsafe_field",
    [
        _field(FieldKind.TEXT, required=True),
        _field(
            FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
        ),
    ],
    ids=("required-data", "identity"),
)
def test_missing_nonnullable_or_identity_field_is_refused(
    pg_schemas, unsafe_field
) -> None:
    # Arrange
    target = _target(pg_schemas)
    old = _open(target, _schema({"status": _field(FieldKind.TEXT)}))
    old.close()

    fields = dict(_schema({"status": _field(FieldKind.TEXT)}).fields)
    fields["unsafe"] = unsafe_field
    attempt = lambda: _open(target, Schema.build("evolution", fields))
    # Act
    operation = attempt
    # Assert
    with pytest.raises(SchemaEvolutionError, match="only DATA fields"):
        operation()


def test_existing_field_with_a_different_physical_type_is_refused(pg_schemas) -> None:
    # Arrange
    target = _target(pg_schemas)
    old = _open(target, _schema({"value": _field(FieldKind.TEXT)}))
    old.close()

    # Act
    operation = lambda: _open(
        target, _schema({"value": _field(FieldKind.INTEGER)})
    )
    # Assert
    with pytest.raises(SchemaEvolutionError, match="Retyping is destructive"):
        operation()


def test_optional_field_with_a_nonnullable_physical_constraint_is_refused(
    pg_schemas,
) -> None:
    # Arrange
    target = _target(pg_schemas)
    schema = _schema({"scope_unit": _field(FieldKind.TEXT)})
    old = _open(target, schema)
    old._connection.execute(
        'ALTER TABLE "evolution_rows" ALTER COLUMN "scope_unit" SET NOT NULL'
    )
    old.close()

    # Act
    operation = lambda: _open(target, schema)
    # Assert
    with pytest.raises(SchemaEvolutionError, match="physically NOT NULL"):
        operation()


def test_concurrent_openers_add_one_field_without_a_schema_race(pg_schemas) -> None:
    # Arrange
    target = _target(pg_schemas)
    old = _open(target, _schema({"status": _field(FieldKind.TEXT)}))
    old.close()
    current = _schema(
        {
            "status": _field(FieldKind.TEXT),
            "scope_invocation_id": _field(FieldKind.TEXT),
        }
    )

    def open_and_observe(index: int) -> tuple[str, ...]:
        store = _open(target, current, node=f"node-{index}")
        try:
            return store.schema_evolution.observed
        finally:
            store.close()

    # Act
    with ThreadPoolExecutor(max_workers=8) as pool:
        observed = list(pool.map(open_and_observe, range(8)))

    # Assert
    assert observed == [("id", "status", "scope_invocation_id")] * 8


def test_new_indexed_optional_field_is_added_before_its_index_is_repaired(
    pg_schemas,
) -> None:
    # Arrange
    target = _target(pg_schemas)
    old = _open(target, _schema({"status": _field(FieldKind.TEXT)}))
    old.close()
    fields = dict(_schema({"status": _field(FieldKind.TEXT)}).fields)
    fields["session_id"] = FieldPolicy(
        kind=FieldKind.TEXT,
        role=FieldRole.DATA,
        required=False,
        merge=MergeRule.LAST_WRITER_WINS,
        indexed=True,
    )

    # Act
    current = _open(target, Schema.build("evolution", fields))
    try:
        index = "evolution_rows_session_id_idx"
        indexes = current._first_column_values(
            current.dialect.indexes_sql("evolution_rows")
        )
        # Assert
        assert index in indexes
    finally:
        current.close()
