"""Operator-only creation of new, private tenant Store namespaces.

Existing unprotected tables are refused, not assigned to a guessed user.
No credential creation, shared-table migration, or production invocation
is implied by this API.
"""

from __future__ import annotations

from ._dialect._postgres import PostgresDialect
from ._errors import StoreProvisionError
from ._policy import Schema
from ._target import StoreTarget
from ._tenant import TenantScope

__all__ = ["provision_tenant_store"]


def provision_tenant_store(
    migration_target: StoreTarget,
    schema: Schema,
    scope: TenantScope,
    *,
    owner_role: str = "scitex_cloud_owner",
) -> None:
    """Provision a new declared store with least-privilege grants and FORCE RLS.

    The operator must create an unprivileged, credentialed tenant LOGIN and
    a separate NOLOGIN owner first. Namespace identity derives from UUID.
    This function never connects as or grants the owner role to a tenant.
    """
    from psycopg import sql

    dialect = PostgresDialect()
    connection = dialect.connect(migration_target)
    # Provisioning reads named catalogue fields, never user data.
    try:
        with connection.transaction():
            namespace = sql.Identifier(scope.namespace)
            principal = sql.Identifier(scope.principal)
            owner = sql.Identifier(owner_role)
            role = connection.execute(
                "SELECT rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb "
                "OR rolreplication OR NOT rolcanlogin AS unsafe "
                "FROM pg_roles WHERE rolname=%s",
                (scope.principal,),
            ).fetchone()
            if role is None or role["unsafe"]:
                raise StoreProvisionError("Create an unprivileged tenant login first.")
            if (
                connection.execute(
                    "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
                    "WHERE r.rolname=%s LIMIT 1",
                    (scope.principal,),
                ).fetchone()
                is not None
            ):
                raise StoreProvisionError(
                    "Tenant logins must not have role memberships."
                )
            owner_found = connection.execute(
                "SELECT rolcanlogin OR rolsuper OR rolbypassrls AS unsafe "
                "FROM pg_roles WHERE rolname=%s",
                (owner_role,),
            ).fetchone()
            if owner_found is None or owner_found["unsafe"]:
                raise StoreProvisionError("Use a separate NOLOGIN, NOBYPASSRLS owner.")
            existing = connection.execute(
                "SELECT pg_get_userbyid(nspowner) AS owner FROM pg_namespace "
                "WHERE nspname=%s",
                (scope.namespace,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                        namespace, owner
                    )
                )
            elif existing["owner"] != owner_role:
                raise StoreProvisionError(
                    "Existing tenant namespace has a different owner."
                )
            connection.execute(
                sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(namespace)
            )
            connection.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(namespace, principal)
            )
            connection.execute(
                sql.SQL("REVOKE CREATE ON SCHEMA {} FROM {}").format(
                    namespace, principal
                )
            )
            # One schema per tenant across packages, so pooled connections of
            # the SAME login retain the same namespace. Forced shared logins
            # are refused by open_tenant_store, not trusted via an app GUC.
            connection.execute(
                sql.SQL("ALTER ROLE {} SET search_path TO {}").format(
                    principal, namespace
                )
            )
            for table in dialect.schema_tables(schema):
                if (
                    connection.execute(
                        "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname=%s AND c.relname=%s",
                        (scope.namespace, table),
                    ).fetchone()
                    is not None
                ):
                    raise StoreProvisionError(
                        "Existing store objects require a separate reviewed migration."
                    )
            connection.execute(sql.SQL("SET LOCAL ROLE {}").format(owner))
            connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(namespace))
            for statement in dialect.create_sql(schema):
                connection.execute(statement)
            # These are part of normal Store initialization; provision them
            # here so tenant roles never need DDL privileges.
            for table, column, column_type, default in dialect.additive_columns(schema):
                columns = connection.execute(dialect.columns_sql(table)).fetchall()
                if column not in {item["column_name"] for item in columns}:
                    connection.execute(
                        dialect.add_column_sql(table, column, column_type, default)
                    )
            predicate = sql.SQL("SESSION_USER = {}").format(
                sql.Literal(scope.principal)
            )
            for table in dialect.schema_tables(schema):
                qualified = sql.Identifier(scope.namespace, table)
                connection.execute(
                    sql.SQL("REVOKE ALL ON TABLE {} FROM PUBLIC").format(qualified)
                )
                connection.execute(
                    sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(
                        qualified
                    )
                )
                connection.execute(
                    sql.SQL("ALTER TABLE {} FORCE ROW LEVEL SECURITY").format(qualified)
                )
                connection.execute(
                    sql.SQL(
                        "CREATE POLICY tenant_access ON {} FOR ALL TO {} USING ({}) WITH CHECK ({})"
                    ).format(qualified, principal, predicate, predicate)
                )
                connection.execute(
                    sql.SQL(
                        "CREATE POLICY tenant_boundary ON {} AS RESTRICTIVE FOR ALL TO PUBLIC "
                        "USING ({}) WITH CHECK ({})"
                    ).format(qualified, predicate, predicate)
                )
                privileges = "SELECT, INSERT"
                if table in (dialect.rows_table(schema), dialect.cursor_table(schema)):
                    privileges += ", UPDATE"
                connection.execute(
                    sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                        sql.SQL(privileges), qualified, principal
                    )
                )
    finally:
        connection.close()
