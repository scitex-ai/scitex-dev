#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A Store's owner and DML role are provisioned as one verified change."""

from __future__ import annotations

import pytest

from scitex_dev.store import (
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    Schema,
    StoreProvisionError,
    StoreTarget,
    inspect_store_acl,
    provision_store_acl,
)
from scitex_dev.store._provision import (
    managed_store_needs_provisioning,
    requires_privileged_provisioning,
)

from .conftest import BASE_DSN


def _current_user() -> str:
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(BASE_DSN) as connection:
        return str(connection.execute("SELECT current_user").fetchone()[0])


def _target(namespace: str) -> StoreTarget:
    joiner = "&" if "?" in BASE_DSN else "?"
    return StoreTarget.postgres(
        f"{BASE_DSN}{joiner}options=-csearch_path%3D{namespace}", pkg="cards"
    )


def test_inspection_reports_a_fresh_store_not_ready(pg_schemas, card_schema) -> None:
    # Arrange
    namespace = pg_schemas("provision_inspect")
    target = _target(namespace)
    role = _current_user()
    # Act
    status = inspect_store_acl(target, card_schema, owner_role=role, writer_role=role)
    # Assert
    assert status.ready is False


def test_provision_creates_owned_dml_ready_store(pg_schemas, card_schema) -> None:
    # Arrange
    namespace = pg_schemas("provision_apply")
    target = _target(namespace)
    role = _current_user()
    # Act
    status = provision_store_acl(target, card_schema, owner_role=role, writer_role=role)
    # Assert
    assert status.ready is True


def test_provision_is_idempotent(pg_schemas, card_schema) -> None:
    # Arrange
    namespace = pg_schemas("provision_twice")
    target = _target(namespace)
    role = _current_user()
    provision_store_acl(target, card_schema, owner_role=role, writer_role=role)
    # Act
    status = provision_store_acl(target, card_schema, owner_role=role, writer_role=role)
    # Assert
    assert status.ready is True


def test_provision_applies_safe_declared_field_evolution(
    pg_schemas, card_schema
) -> None:
    # Arrange
    namespace = pg_schemas("provision_evolve")
    target = _target(namespace)
    role = _current_user()
    provision_store_acl(target, card_schema, owner_role=role, writer_role=role)
    evolved = Schema.build(
        card_schema.name,
        {
            **card_schema.fields,
            "summary": FieldPolicy(
                kind=FieldKind.TEXT,
                role=FieldRole.DATA,
                required=False,
                merge=MergeRule.LAST_WRITER_WINS,
                indexed=False,
            ),
        },
    )
    # Act
    provision_store_acl(target, evolved, owner_role=role, writer_role=role)
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(target.dsn) as connection:
        found = connection.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='cards_rows' "
            "AND column_name='summary'"
        ).fetchone()
    # Assert
    assert found is not None


def test_provision_rejects_an_unquoted_role_surface(card_schema) -> None:
    # Arrange
    target = StoreTarget.postgres(BASE_DSN, pkg="cards")
    # Act
    caught = None
    try:
        inspect_store_acl(
            target,
            card_schema,
            owner_role='owner"; DROP TABLE tasks; --',
        )
    except StoreProvisionError as exc:
        caught = exc
    # Assert
    assert "letters, digits and underscores" in str(caught)


class _RoleConnection:
    def execute(self, _statement, _params):
        return self

    def fetchall(self):
        return [{"rolname": "scitex_store_owner"}, {"rolname": "scitex_rw"}]


class _ManagedConnection:
    def __init__(self) -> None:
        self.rows = []

    def execute(self, statement, _params=None):
        if "FROM pg_roles" in statement:
            self.rows = [
                {"rolname": "scitex_store_owner"},
                {"rolname": "scitex_rw"},
            ]
        elif "column_name, udt_name" in statement:
            self.rows = [{"column_name": "id"}]
        else:
            self.rows = []
        return self

    def fetchall(self):
        return self.rows


class _ManagedDialect:
    @staticmethod
    def rows_table(_schema):
        return "cards_rows"

    @staticmethod
    def column_definitions_sql(_table):
        return "SELECT column_name, udt_name"

    @staticmethod
    def additive_columns(_schema):
        return ()


def test_database_with_both_managed_roles_requires_provisioning() -> None:
    # Arrange
    connection = _RoleConnection()
    # Act
    required = requires_privileged_provisioning(connection)
    # Assert
    assert required is True


def test_managed_database_routes_missing_declared_fields_to_provisioner(
    card_schema,
) -> None:
    # Arrange
    connection = _ManagedConnection()
    dialect = _ManagedDialect()
    # Act
    required = managed_store_needs_provisioning(
        connection,
        dialect,
        card_schema,
        rows_exist=True,
        schema_objects_missing=False,
    )
    # Assert
    assert required is True


def test_failed_provision_rolls_back_all_schema_changes(
    pg_schemas, card_schema
) -> None:
    # Arrange
    psycopg = pytest.importorskip("psycopg")
    namespace = pg_schemas("provision_rollback")
    target = _target(namespace)
    # Act
    caught = None
    try:
        provision_store_acl(
            target,
            card_schema,
            owner_role=_current_user(),
            writer_role="role_that_does_not_exist",
        )
    except StoreProvisionError as exc:
        caught = exc
    with psycopg.connect(BASE_DSN) as connection:
        count = connection.execute(
            "SELECT count(*) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=%s AND c.relname LIKE 'cards_%%'",
            (namespace,),
        ).fetchone()[0]
    # Assert
    assert (isinstance(caught, StoreProvisionError), count) == (True, 0)


# EOF
