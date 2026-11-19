"""Adversarial PostgreSQL experiments with synthetic users and rows only."""

from __future__ import annotations

import secrets
from contextlib import ExitStack
from urllib.parse import quote, urlencode
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from scitex_dev.store import NEW_RECORD, StoreTarget, WriterPolicy
from scitex_dev.store._dialect._postgres import PostgresDialect
from scitex_dev.store._errors import StoreProvisionError, StoreTargetError
from scitex_dev.store._tenant import (
    TenantScope,
    inspect_tenant_store,
    open_tenant_store,
)
from scitex_dev.store._tenant_provision import provision_tenant_store

from .conftest import BASE_DSN


@pytest.fixture
def tenants(card_schema):
    scopes = (TenantScope(uuid4()), TenantScope(uuid4()))
    owner = f"tenant_test_owner_{uuid4().hex[:12]}"
    passwords = {scope.principal: secrets.token_urlsafe(32) for scope in scopes}
    with psycopg.connect(BASE_DSN, autocommit=True) as admin, ExitStack() as cleanup:
        port = admin.info.port
        if port in {55432, 55433}:
            pytest.fail("These synthetic experiments refuse the managed store ports.")
        admin.execute(
            sql.SQL("CREATE ROLE {} NOLOGIN NOBYPASSRLS").format(sql.Identifier(owner))
        )
        cleanup.callback(
            admin.execute,
            sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(owner)),
        )
        for scope in scopes:
            admin.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(
                    sql.Identifier(scope.principal),
                    sql.Literal(passwords[scope.principal]),
                )
            )
            cleanup.callback(
                admin.execute,
                sql.SQL("DROP ROLE IF EXISTS {}").format(
                    sql.Identifier(scope.principal)
                ),
            )
        migration = StoreTarget.postgres(BASE_DSN, pkg="tenant_test")
        for scope in scopes:
            cleanup.callback(
                admin.execute,
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(scope.namespace)
                ),
            )
            provision_tenant_store(migration, card_schema, scope, owner_role=owner)

        def target(scope):
            # Preserve the selected socket/port; native CI is socket-only.
            selected = conninfo_to_dict(BASE_DSN)
            selected.update(user=scope.principal, password=passwords[scope.principal])
            database = selected.pop("dbname", admin.info.dbname)
            dsn = f"postgresql:///{quote(database, safe='')}?{urlencode(selected)}"
            return StoreTarget.postgres(dsn, pkg="tenant_test")

        def opened(scope):
            store = open_tenant_store(
                target(scope),
                card_schema,
                scope,
                node="synthetic_web",
                writer_policy=WriterPolicy.MULTI_WRITER,
                owner_role=owner,
            )
            cleanup.callback(store.close)
            return store

        a, b = (opened(scope) for scope in scopes)
        a.put({"id": "same-id", "status": "alice-secret"}, expected_revision=NEW_RECORD)
        b.put({"id": "same-id", "status": "bob-secret"}, expected_revision=NEW_RECORD)
        yield admin, scopes, owner, target, opened, a, b


def test_read_apis_return_only_the_authenticated_tenants_rows(tenants):
    # Arrange
    _admin, _scopes, _owner, _target, _opened, a, b = tenants
    # Act
    for store, expected in [(a, "alice-secret"), (b, "bob-secret")]:
        observed = (
            [row.values["status"] for row in store.rows()],
            [row.values["status"] for row in store.search()],
            store.get({"id": "same-id"}).values["status"],
            store.count(),
            store.tally("status"),
        )
        # Assert
        assert observed == ([expected], [expected], expected, 1, {expected: 1})


def test_all_store_tables_have_forced_restrictive_rls(tenants, card_schema):
    # Arrange
    _admin, scopes, owner, target, _opened, _a, _b = tenants
    # Act
    for scope in scopes:
        with psycopg.connect(target(scope).dsn) as connection:
            # Assert
            assert inspect_tenant_store(
                connection, card_schema, scope, owner_role=owner
            ).ready


def test_raw_queries_cannot_read_another_namespace(tenants):
    # Arrange
    _admin, scopes, _owner, target, _opened, _a, _b = tenants
    # Act
    a, b = scopes
    # Assert
    with (
        psycopg.connect(target(a).dsn, autocommit=True) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(
            sql.SQL("SELECT * FROM {}").format(
                sql.Identifier(b.namespace, "cards_rows")
            )
        )


def test_rls_survives_accidental_cross_tenant_grants(tenants, card_schema):
    # Arrange
    admin, scopes, _owner, target, _opened, _a, _b = tenants
    # Act
    a, b = scopes
    admin.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(b.namespace), sql.Identifier(a.principal)
        )
    )
    for table in PostgresDialect().schema_tables(card_schema):
        admin.execute(
            sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(
                sql.Identifier(b.namespace, table), sql.Identifier(a.principal)
            )
        )
        with psycopg.connect(target(a).dsn) as connection:
            # Assert
            assert (
                connection.execute(
                    sql.SQL("SELECT * FROM {}").format(
                        sql.Identifier(b.namespace, table)
                    )
                ).fetchall()
                == []
            )


def test_restrictive_boundary_survives_a_broad_permissive_policy(tenants):
    # Arrange
    admin, scopes, _owner, target, _opened, _a, _b = tenants
    # Act
    a, b = scopes
    qualified = sql.Identifier(b.namespace, "cards_rows")
    admin.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(b.namespace), sql.Identifier(a.principal)
        )
    )
    admin.execute(
        sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(
            qualified, sql.Identifier(a.principal)
        )
    )
    admin.execute(
        sql.SQL("CREATE POLICY accidental_allow ON {} USING (true)").format(qualified)
    )
    with psycopg.connect(target(a).dsn) as connection:
        # Assert
        assert (
            connection.execute(sql.SQL("SELECT * FROM {}").format(qualified)).fetchall()
            == []
        )


def _grant_foreign_dml(tenants):
    admin, scopes, _owner, target, _opened, _a, b_store = tenants
    a, b = scopes
    admin.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(b.namespace), sql.Identifier(a.principal)
        )
    )
    admin.execute(
        sql.SQL("GRANT SELECT, INSERT, UPDATE ON TABLE {} TO {}").format(
            sql.Identifier(b.namespace, "cards_rows"), sql.Identifier(a.principal)
        )
    )
    return a, b, target, b_store


def test_cross_tenant_updates_do_not_change_rows_after_accidental_grants(tenants):
    # Arrange
    a, b, target, b_store = _grant_foreign_dml(tenants)
    # Act
    with psycopg.connect(target(a).dsn, autocommit=True) as connection:
        rows = connection.execute(
            sql.SQL("UPDATE {} SET status='stolen' RETURNING _record").format(
                sql.Identifier(b.namespace, "cards_rows")
            )
        ).fetchall()
    # Assert
    assert (rows, b_store.get({"id": "same-id"}).values["status"]) == ([], "bob-secret")


def test_cross_tenant_inserts_fail_after_accidental_grants(tenants):
    # Arrange
    a, b, target, _b_store = _grant_foreign_dml(tenants)
    # Act
    # Assert
    with (
        psycopg.connect(target(a).dsn, autocommit=True) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(
            sql.SQL("INSERT INTO {} SELECT * FROM {}").format(
                sql.Identifier(b.namespace, "cards_rows"),
                sql.Identifier(a.namespace, "cards_rows"),
            )
        )


def test_user_settable_context_cannot_change_authenticated_identity(tenants):
    # Arrange
    _admin, scopes, _owner, target, _opened, _a, _b = tenants
    # Act
    a, b = scopes
    with psycopg.connect(target(a).dsn) as connection:
        connection.execute(
            "SELECT set_config('app.tenant_id', %s, false)", (str(b.tenant_id),)
        )
        # Assert
        assert connection.execute("SELECT status FROM cards_rows").fetchall() == [
            ("alice-secret",)
        ]


@pytest.mark.parametrize(
    "operation", ["SET ROLE {role}", "SET SESSION AUTHORIZATION {role}"]
)
def test_a_tenant_cannot_impersonate_another_login(tenants, operation):
    # Arrange
    _admin, scopes, _owner, target, _opened, _a, _b = tenants
    # Act
    a, b = scopes
    # Assert
    with (
        psycopg.connect(target(a).dsn, autocommit=True) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(sql.SQL(operation).format(role=sql.Identifier(b.principal)))


def test_a_tenant_cannot_disable_rls(tenants):
    # Arrange
    _admin, scopes, _owner, target, _opened, _a, _b = tenants
    # Act
    # Assert
    with (
        psycopg.connect(target(scopes[0]).dsn) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute("ALTER TABLE cards_rows DISABLE ROW LEVEL SECURITY")


def test_shared_admin_credentials_are_refused(tenants, card_schema):
    # Arrange
    _admin, scopes, owner, _target, _opened, _a, _b = tenants
    # Act
    # Assert
    with pytest.raises(StoreTargetError, match="principal differs"):
        open_tenant_store(
            StoreTarget.postgres(BASE_DSN, pkg="tenant_test"),
            card_schema,
            scopes[0],
            node="web",
            writer_policy=WriterPolicy.MULTI_WRITER,
            owner_role=owner,
        )


def test_missing_boundary_is_refused_before_store_reads(tenants):
    # Arrange
    admin, scopes, _owner, _target, opened, _a, _b = tenants
    # Act
    admin.execute(
        sql.SQL("DROP POLICY tenant_boundary ON {}").format(
            sql.Identifier(scopes[0].namespace, "cards_oplog")
        )
    )
    # Assert
    with pytest.raises(StoreTargetError, match="boundary is missing"):
        opened(scopes[0])


@pytest.mark.parametrize(
    "policy_change",
    [
        "DROP POLICY tenant_access ON {}",
        "CREATE POLICY deny_self ON {} AS RESTRICTIVE USING (false)",
    ],
)
def test_denied_access_is_unavailable_instead_of_empty(
    tenants, card_schema, policy_change
):
    # Arrange
    admin, scopes, owner, target, _opened, _a, _b = tenants
    scope = scopes[0]
    admin.execute(
        sql.SQL(policy_change).format(sql.Identifier(scope.namespace, "cards_rows"))
    )
    # Act
    with psycopg.connect(target(scope).dsn) as connection:
        rows = connection.execute("SELECT * FROM cards_rows").fetchall()
        status = inspect_tenant_store(connection, card_schema, scope, owner_role=owner)
    # Assert
    assert (rows, status.ready) == ([], False)


def test_provisioning_will_not_adopt_existing_tables(tenants, card_schema):
    # Arrange
    _admin, scopes, owner, _target, _opened, _a, _b = tenants
    # Act
    # Assert
    with pytest.raises(StoreProvisionError, match="reviewed migration"):
        provision_tenant_store(
            StoreTarget.postgres(BASE_DSN, pkg="tenant_test"),
            card_schema,
            scopes[0],
            owner_role=owner,
        )


@pytest.mark.parametrize("operation", ["DELETE FROM cards_rows", "TRUNCATE cards_rows"])
def test_destructive_sql_is_not_granted(tenants, operation):
    # Arrange
    _admin, scopes, _owner, target, _opened, _a, _b = tenants
    # Act
    # Assert
    with (
        psycopg.connect(target(scopes[0]).dsn) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(operation)


def test_destructive_grant_is_detected_before_open(tenants):
    # Arrange
    admin, scopes, _owner, _target, opened, _a, _b = tenants
    # Act
    admin.execute(
        sql.SQL("GRANT TRUNCATE ON TABLE {} TO {}").format(
            sql.Identifier(scopes[0].namespace, "cards_rows"),
            sql.Identifier(scopes[0].principal),
        )
    )
    # Assert
    with pytest.raises(StoreTargetError, match="destructive table privileges"):
        opened(scopes[0])


@pytest.mark.parametrize("value", [UUID(int=0), "alice", None])
def test_no_display_name_or_missing_identity_is_accepted(value):
    # Arrange
    # Act
    # Assert
    with pytest.raises(StoreTargetError):
        TenantScope(value)
