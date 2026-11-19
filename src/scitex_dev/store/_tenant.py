"""Cloud tenant access authenticated by PostgreSQL, independent of row owner.

One stable user UUID maps to a private namespace and unprivileged login.
Existing shared stores are unchanged; using this API requires provisioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ._dialect._postgres import PostgresDialect
from ._errors import StoreTargetError
from ._policy import Schema, WriterPolicy
from ._target import StoreTarget

__all__ = [
    "TenantScope",
    "TenantStoreStatus",
    "inspect_tenant_store",
    "open_tenant_store",
]


@dataclass(frozen=True, slots=True)
class TenantScope:
    """Identity resolved by the server, never a request-supplied username."""

    tenant_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID) or self.tenant_id.int == 0:
            raise StoreTargetError("A nonzero stable user UUID is required.")

    @property
    def principal(self) -> str:
        return f"scitex_t_{self.tenant_id.hex}"

    @property
    def namespace(self) -> str:
        return f"scitex_u_{self.tenant_id.hex}"


@dataclass(frozen=True, slots=True)
class TenantStoreStatus:
    """Catalogue evidence, collected without reading user rows."""

    principal: str
    namespace: str
    issues: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.issues


def _mapping(row: Any, names: tuple[str, ...]) -> dict:
    return dict(row) if hasattr(row, "keys") else dict(zip(names, row))


def _predicate(expression: str | None, scope: TenantScope) -> bool:
    normalized = " ".join((expression or "").lower().split()).strip("() ")
    return normalized == f"session_user = '{scope.principal}'::name"


def _access_policy_ready(connection: Any, table: str, scope: TenantScope) -> bool:
    found = connection.execute(
        "SELECT p.polpermissive, p.polcmd, p.polroles=ARRAY[r.oid] AS tenant_only, "
        "pg_get_expr(p.polqual, p.polrelid) AS qual, "
        "pg_get_expr(p.polwithcheck, p.polrelid) AS check_expression, "
        "EXISTS (SELECT 1 FROM pg_policy other WHERE other.polrelid=c.oid "
        "AND NOT other.polpermissive AND other.polname<>'tenant_boundary') "
        "AS unexpected_restriction "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_policy p ON p.polrelid=c.oid AND p.polname='tenant_access' "
        "JOIN pg_roles r ON r.rolname=%s "
        "WHERE n.nspname=%s AND c.relname=%s AND c.relkind='r'",
        (scope.principal, scope.namespace, table),
    ).fetchone()
    if found is None:
        return False
    values = _mapping(
        found,
        (
            "polpermissive",
            "polcmd",
            "tenant_only",
            "qual",
            "check_expression",
            "unexpected_restriction",
        ),
    )
    return (
        values["polpermissive"] is True
        and values["polcmd"] == "*"
        and values["tenant_only"] is True
        and _predicate(values["qual"], scope)
        and _predicate(values["check_expression"], scope)
        and not values["unexpected_restriction"]
    )


def inspect_tenant_store(
    connection: Any,
    schema: Schema,
    scope: TenantScope,
    *,
    owner_role: str = "scitex_cloud_owner",
) -> TenantStoreStatus:
    """Refuse shared credentials, elevation, ownership, or weakened RLS.

    All four Store tables are covered, including payloads in the oplog and
    state in cursor/identity tables. A pool must retain the authenticated
    principal and namespace; a forced shared backend identity fails closed.
    """
    issues: list[str] = []
    identity = _mapping(
        connection.execute(
            "SELECT session_user::text, current_user::text, current_schema()"
        ).fetchone(),
        ("session_user", "current_user", "current_schema"),
    )
    if identity["session_user"] != scope.principal:
        issues.append("authenticated principal differs from the resolved tenant")
    if identity["current_user"] != scope.principal:
        issues.append("effective role differs from the resolved tenant")
    if identity["current_schema"] != scope.namespace:
        issues.append("connection is outside the tenant namespace")
    role = connection.execute(
        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolreplication, "
        "rolcanlogin FROM pg_roles WHERE rolname=%s",
        (scope.principal,),
    ).fetchone()
    if role is None:
        issues.append("tenant login is missing")
    else:
        flags = _mapping(
            role,
            (
                "rolsuper",
                "rolbypassrls",
                "rolcreaterole",
                "rolcreatedb",
                "rolreplication",
                "rolcanlogin",
            ),
        )
        if not flags["rolcanlogin"] or any(
            v for k, v in flags.items() if k != "rolcanlogin"
        ):
            issues.append("tenant login has unsafe PostgreSQL attributes")
    if (
        connection.execute(
            "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
            "WHERE r.rolname=%s LIMIT 1",
            (scope.principal,),
        ).fetchone()
        is not None
    ):
        issues.append("tenant login has role memberships")
    if (
        connection.execute(
            "SELECT 1 FROM pg_namespace WHERE nspname=%s "
            "AND has_schema_privilege(%s, oid, 'CREATE')",
            (scope.namespace, scope.principal),
        ).fetchone()
        is not None
    ):
        issues.append("tenant login can create namespace objects")
    for table in PostgresDialect().schema_tables(schema):
        if (
            connection.execute(
                "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=%s AND c.relname=%s AND ("
                "has_table_privilege(%s, c.oid, 'TRUNCATE') OR "
                "has_table_privilege(%s, c.oid, 'DELETE'))",
                (scope.namespace, table, scope.principal, scope.principal),
            ).fetchone()
            is not None
        ):
            issues.append(f"{table}: destructive table privileges are granted")
        found = connection.execute(
            "SELECT pg_get_userbyid(c.relowner) AS owner, c.relrowsecurity, "
            "c.relforcerowsecurity, p.polpermissive, p.polcmd, p.polroles, "
            "pg_get_expr(p.polqual, p.polrelid) AS qual, "
            "pg_get_expr(p.polwithcheck, p.polrelid) AS check_expression "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "LEFT JOIN pg_policy p ON p.polrelid=c.oid AND p.polname='tenant_boundary' "
            "WHERE n.nspname=%s AND c.relname=%s AND c.relkind='r'",
            (scope.namespace, table),
        ).fetchone()
        if found is None:
            issues.append(f"{table}: not provisioned")
            continue
        values = _mapping(
            found,
            (
                "owner",
                "relrowsecurity",
                "relforcerowsecurity",
                "polpermissive",
                "polcmd",
                "polroles",
                "qual",
                "check_expression",
            ),
        )
        if values["owner"] != owner_role:
            issues.append(f"{table}: unexpected table owner")
        if not values["relrowsecurity"] or not values["relforcerowsecurity"]:
            issues.append(f"{table}: RLS is not enabled and forced")
        if (
            values["polpermissive"] is not False
            or values["polcmd"] != "*"
            or list(values["polroles"] or ()) != [0]
            or not _predicate(values["qual"], scope)
            or not _predicate(values["check_expression"], scope)
        ):
            issues.append(f"{table}: restrictive tenant boundary is missing or changed")
        if not _access_policy_ready(connection, table, scope):
            issues.append(f"{table}: tenant access policy is missing or changed")
    return TenantStoreStatus(scope.principal, scope.namespace, tuple(issues))


def open_tenant_store(
    target: StoreTarget,
    schema: Schema,
    scope: TenantScope,
    *,
    node: str,
    writer_policy: WriterPolicy,
    actor: str = "",
    owner_role: str = "scitex_cloud_owner",
):
    """Open only a pre-provisioned tenant store, without a shared fallback."""
    from ._store import Store

    class TenantDialect(PostgresDialect):
        def connect(self, selected: StoreTarget):
            connection = super().connect(selected)
            try:
                status = inspect_tenant_store(
                    connection, schema, scope, owner_role=owner_role
                )
                if not status.ready:
                    raise StoreTargetError(
                        "Tenant store refused: " + "; ".join(status.issues)
                    )
            except BaseException:
                connection.close()
                raise
            return connection

    return Store(
        target,
        schema,
        node=node,
        actor=actor,
        writer_policy=writer_policy,
        dialect=TenantDialect(),
    )
