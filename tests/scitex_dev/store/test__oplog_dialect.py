#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The target, the placeholder translation, and the tables both engines build.

One DDL set serves SQLite and PostgreSQL, which is only safe if it is
verified on both -- so the table-existence checks run through the same
``dialect`` fixture as everything else and ask the LIVE database what it
created. The rest is the small amount of dialect knowledge that has to
exist somewhere: which placeholder each engine speaks, and the refusal to
guess when handed a dialect that is neither.
"""

from __future__ import annotations

from scitex_dev.store._oplog_dialect import (
    DDL_STATEMENTS,
    POSTGRES,
    SQLITE,
    OplogTarget,
    placeholder_for,
    record_apply_sql,
    translate,
)

SQL = "SELECT payload FROM stx_record WHERE record_key = ?"


def _target(**overrides):
    fields = {"dialect": SQLITE, "dsn": "/tmp/unused.sqlite3"}
    fields.update(overrides)
    try:
        return OplogTarget(**fields)
    except Exception as exc:
        return exc


# --- placeholders ----------------------------------------------------------


def test_sqlite_speaks_question_marks():
    # Arrange
    dialect = SQLITE
    # Act
    placeholder = placeholder_for(dialect)
    # Assert
    assert placeholder == "?"


def test_postgres_speaks_percent_s():
    # Arrange
    dialect = POSTGRES
    # Act
    placeholder = placeholder_for(dialect)
    # Assert
    assert placeholder == "%s"


def test_translation_rewrites_placeholders_for_postgres():
    # Arrange
    sql = SQL
    # Act
    rendered = translate(sql, POSTGRES)
    # Assert
    assert rendered.endswith("= %s")


def test_translation_leaves_sqlite_untouched():
    # Arrange
    sql = SQL
    # Act
    rendered = translate(sql, SQLITE)
    # Assert
    assert rendered == sql


# --- the target ------------------------------------------------------------


def test_an_unknown_dialect_is_refused():
    # Arrange
    dialect = "mysql"
    # Act
    outcome = _target(dialect=dialect)
    # Assert
    assert isinstance(outcome, ValueError)


def test_the_refusal_names_the_supported_dialects():
    # Arrange
    dialect = "mysql"
    # Act
    outcome = _target(dialect=dialect)
    # Assert
    assert "postgres" in str(outcome)


def test_a_target_defaults_to_no_namespace():
    # Arrange
    dialect = SQLITE
    # Act
    target = _target(dialect=dialect)
    # Assert
    assert target.namespace == ""


# --- the shared statement set ---------------------------------------------


def test_every_table_is_created_idempotently():
    # Arrange
    statements = DDL_STATEMENTS
    # Act
    guarded = [text for text in statements if "IF NOT EXISTS" in text]
    # Assert
    assert len(guarded) == len(statements)


def test_the_apply_statement_is_guarded_against_replays():
    """The guard is what makes applying an op twice a no-op."""
    # Arrange
    sql = record_apply_sql()
    # Act
    guarded = "stx_record.seq < excluded.seq" in sql
    # Assert
    assert guarded is True


# --- what the engines actually build --------------------------------------


def test_the_oplog_table_exists_on_the_engine(store):
    # Arrange
    table = "stx_oplog"
    # Act
    columns = store.columns_of(table)
    # Assert
    assert len(columns) == 8


def test_the_cursor_table_exists_on_the_engine(store):
    # Arrange
    table = "stx_cursor"
    # Act
    columns = store.columns_of(table)
    # Assert
    assert "applied_seq" in columns


def test_the_fence_table_exists_on_the_engine(store):
    # Arrange
    table = "stx_fence"
    # Act
    columns = store.columns_of(table)
    # Assert
    assert "fence" in columns


def test_the_record_table_exists_on_the_engine(store):
    # Arrange
    table = "stx_record"
    # Act
    columns = store.columns_of(table)
    # Assert
    assert "record_key" in columns


# EOF
