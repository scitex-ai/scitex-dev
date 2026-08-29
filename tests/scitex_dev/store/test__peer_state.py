#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Opening a store must not require the right to CREATE it.

Mirrors ``src/scitex_dev/store/_peer_state.py``, which owns the
``_schema_objects_missing`` probe these tests pin.

Every statement in ``create_sql`` carries IF NOT EXISTS, so re-running it on
an existing store looked free. On PostgreSQL it is not: ownership is checked
BEFORE that clause short-circuits, so ``CREATE INDEX IF NOT EXISTS`` naming an
index that already exists still raises InsufficientPrivilege for a role that
does not own the table. A role holding SELECT/INSERT/UPDATE/DELETE on every
table of a store therefore could not OPEN it at all.

Measured 2026-08-28 against the fleet primary, as a member of the grant role:

    SELECT / INSERT                       OK
    CREATE INDEX IF NOT EXISTS (exists)   must be owner of table ...
    ALTER TABLE ADD COLUMN IF NOT EXISTS  must be owner of table ...

WHY THE TESTS BELOW LOOK LIKE THIS. Skipping DDL is only safe if the probe is
CONSERVATIVE — it must report "missing" for anything ``create_sql`` would
build, or the skip silently stops creating things. So the interesting cases
are not the happy path but the three ways an object can be absent: a dropped
index, a dropped table, and an index the schema gained after the store was
made. That last one is the regression this design could plausibly introduce,
and it gets a test for exactly that reason.

Everything here runs on a real PostgreSQL schema, which is where the probe
dialect-neutral and its logic is what these tests pin; the privilege
behaviour itself belongs to the server, not to this package.
"""

from __future__ import annotations

import pytest

from .conftest import BASE_DSN

from scitex_dev.store import (
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    Schema,
    Store,
    StoreTarget,
    WriterPolicy,
)


@pytest.fixture
def probe_schema(pg_schemas) -> str:
    """The schema ``store`` lives in, so a test can reopen the same store."""
    return pg_schemas("probe")


@pytest.fixture
def store(probe_schema, card_schema) -> Store:
    """A created store, so every object create_sql builds is present."""
    dsn = f"{BASE_DSN}?options=-csearch_path%3D{probe_schema}"
    store = Store(
        StoreTarget.postgres(dsn, pkg="cards"),
        card_schema,
        node="node-probe",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def schema_with_an_extra_index(card_schema) -> Schema:
    """``card_schema`` with ``id`` newly indexed.

    The column already exists, so only the INDEX is missing — which is what
    adding an index to a deployed store actually looks like.
    """
    fields = dict(card_schema.fields)
    fields["id"] = FieldPolicy(
        kind=FieldKind.TEXT,
        role=FieldRole.IDENTITY,
        required=True,
        merge=MergeRule.IMMUTABLE,
        indexed=True,
    )
    return Schema.build("cards", fields)


# ---------------------------------------------------------------------------
# the happy path — this is what makes the skip possible at all
# ---------------------------------------------------------------------------


def test_a_created_store_reports_nothing_missing(store, card_schema) -> None:
    # Arrange
    schema = card_schema
    # Act
    missing = store._schema_objects_missing(schema)
    # Assert
    assert missing is False


# ---------------------------------------------------------------------------
# ... and the three ways it must still say "missing"
# ---------------------------------------------------------------------------


def test_a_dropped_index_is_reported_missing(store, card_schema) -> None:
    # Arrange
    index, _table, _column = store.dialect.index_specs(card_schema)[0]
    store._connection.execute(f"DROP INDEX {store.dialect.quote(index)}")
    # Act
    missing = store._schema_objects_missing(card_schema)
    # Assert
    assert missing is True


def test_a_dropped_table_is_reported_missing(store, card_schema) -> None:
    # Arrange
    cursor_table = store.dialect.cursor_table(card_schema)
    store._connection.execute(f"DROP TABLE {store.dialect.quote(cursor_table)}")
    # Act
    missing = store._schema_objects_missing(card_schema)
    # Assert
    assert missing is True


def test_an_index_added_to_the_schema_later_is_reported_missing(
    store, schema_with_an_extra_index
) -> None:
    # Arrange — the store predates the new index; the column is already there.
    schema = schema_with_an_extra_index
    # Act
    missing = store._schema_objects_missing(schema)
    # Assert
    assert missing is True


# ---------------------------------------------------------------------------
# the two lists must not drift apart
# ---------------------------------------------------------------------------


def test_create_sql_emits_one_index_statement_per_spec(store, card_schema) -> None:
    # Arrange
    statements = store.dialect.create_sql(card_schema)
    # Act
    emitted = [s for s in statements if s.startswith("CREATE INDEX")]
    # Assert
    assert len(emitted) == len(store.dialect.index_specs(card_schema))


def test_every_index_spec_is_named_by_a_create_statement(store, card_schema) -> None:
    # Arrange
    statements = "\n".join(store.dialect.create_sql(card_schema))
    # Act
    unnamed = [i for i, _t, _c in store.dialect.index_specs(card_schema) if i not in statements]
    # Assert
    assert unnamed == []


def test_schema_tables_names_every_table_create_sql_builds(store, card_schema) -> None:
    # Arrange
    statements = "\n".join(store.dialect.create_sql(card_schema))
    # Act
    unbuilt = [t for t in store.dialect.schema_tables(card_schema) if t not in statements]
    # Assert
    assert unbuilt == []


# ---------------------------------------------------------------------------
# end to end: a store whose index went missing gets it back on reopen
# ---------------------------------------------------------------------------


def test_reopening_recreates_an_index_that_went_missing(
    probe_schema, card_schema, store
) -> None:
    # Arrange
    index, _table, _column = store.dialect.index_specs(card_schema)[0]
    store._connection.execute(f"DROP INDEX {store.dialect.quote(index)}")
    store.close()
    # Act
    reopened = Store(
        StoreTarget.postgres(
            f"{BASE_DSN}?options=-csearch_path%3D{probe_schema}", pkg="cards"
        ),
        card_schema,
        node="node-probe",
        writer_policy=WriterPolicy.MULTI_WRITER,
    )
    # Assert
    assert reopened._schema_objects_missing(card_schema) is False
