#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Privileged PostgreSQL provisioning for a declared Store schema.

Application roles open and use stores; they do not own or repair their DDL.
This module is the explicit operator boundary that creates/normalises Store
objects under one owner role and grants the shared writer role its DML.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from ._errors import StoreProvisionError
from ._policy import Schema
from ._schema_evolution import SchemaEvolution
from ._target import StoreTarget

DEFAULT_OWNER_ROLE: Final[str] = "scitex_store_owner"
DEFAULT_WRITER_ROLE: Final[str] = "scitex_rw"
REQUIRED_DML: Final[tuple[str, ...]] = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
)


@dataclass(frozen=True, slots=True)
class StoreAclStatus:
    """Observed owner/grant state after no mutation or after provisioning."""

    current_user: str
    namespace: str
    owner_role: str
    writer_role: str
    table_owners: tuple[tuple[str, str | None], ...]
    missing_dml: tuple[tuple[str, tuple[str, ...]], ...]
    missing_default_dml: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return (
            all(owner == self.owner_role for _table, owner in self.table_owners)
            and not self.missing_dml
            and not self.missing_default_dml
        )


def _role(role: str, *, field: str) -> str:
    if not role or not role.replace("_", "a").isalnum():
        raise StoreProvisionError(
            f"{field}={role!r} is not a simple PostgreSQL role name. "
            "Provisioning only accepts letters, digits and underscores; "
            "create the intended role explicitly and pass its exact name."
        )
    return role


def _first(row: Any) -> Any:
    return row[next(iter(row.keys()))] if hasattr(row, "keys") else row[0]


def _inspect(
    connection: Any,
    schema: Schema,
    *,
    owner_role: str,
    writer_role: str,
) -> StoreAclStatus:
    namespace = str(_first(connection.execute("SELECT current_schema()").fetchone()))
    current_user = str(_first(connection.execute("SELECT current_user").fetchone()))
    owners: list[tuple[str, str | None]] = []
    missing: list[tuple[str, tuple[str, ...]]] = []
    for table in _dialect().schema_tables(schema):
        found = connection.execute(
            "SELECT pg_get_userbyid(c.relowner) AS owner "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=current_schema() AND c.relname=%s AND c.relkind='r'",
            (table,),
        ).fetchone()
        owner = None if found is None else str(_first(found))
        owners.append((table, owner))
        absent = REQUIRED_DML
        if owner is not None:
            absent = tuple(
                privilege
                for privilege in REQUIRED_DML
                if not bool(
                    _first(
                        connection.execute(
                            "SELECT has_table_privilege(%s, %s, %s)",
                            (writer_role, f"{namespace}.{table}", privilege),
                        ).fetchone()
                    )
                )
            )
        if absent:
            missing.append((table, absent))
    granted = {
        str(_first(row))
        for row in connection.execute(
            "SELECT privilege_type FROM pg_default_acl d "
            "JOIN pg_namespace n ON n.oid=d.defaclnamespace "
            "CROSS JOIN LATERAL aclexplode(d.defaclacl) a "
            "JOIN pg_roles owner ON owner.oid=d.defaclrole "
            "JOIN pg_roles grantee ON grantee.oid=a.grantee "
            "WHERE owner.rolname=%s AND grantee.rolname=%s "
            "AND n.nspname=current_schema() AND d.defaclobjtype='r'",
            (owner_role, writer_role),
        ).fetchall()
    }
    return StoreAclStatus(
        current_user=current_user,
        namespace=namespace,
        owner_role=owner_role,
        writer_role=writer_role,
        table_owners=tuple(owners),
        missing_dml=tuple(missing),
        missing_default_dml=tuple(p for p in REQUIRED_DML if p not in granted),
    )


def _dialect():
    """Return the one Store dialect without making the connection a target."""
    from ._dialect import get_dialect
    from ._target import Backend

    return get_dialect(Backend.POSTGRES)


def inspect_store_acl(
    target: StoreTarget,
    schema: Schema,
    *,
    owner_role: str = DEFAULT_OWNER_ROLE,
    writer_role: str = DEFAULT_WRITER_ROLE,
) -> StoreAclStatus:
    """Read owner, current DML and future-object defaults; change nothing."""
    owner_role = _role(owner_role, field="owner_role")
    writer_role = _role(writer_role, field="writer_role")
    dialect = _dialect()
    connection = dialect.connect(target)
    try:
        return _inspect(
            connection, schema, owner_role=owner_role, writer_role=writer_role
        )
    finally:
        connection.close()


def provision_store_acl(
    target: StoreTarget,
    schema: Schema,
    *,
    owner_role: str = DEFAULT_OWNER_ROLE,
    writer_role: str = DEFAULT_WRITER_ROLE,
) -> StoreAclStatus:
    """Create/repair one Store under ``owner_role`` and prove its DML grant.

    This is intentionally privileged and transactional. A caller unable to
    re-own an existing table or set the owner role gets a refusal and every
    attempted change rolls back. Applications call :class:`Store`; only a
    deployment/migration process calls this function.
    """
    owner_role = _role(owner_role, field="owner_role")
    writer_role = _role(writer_role, field="writer_role")
    dialect = _dialect()
    connection = dialect.connect(target)
    owner = dialect.quote(owner_role)
    writer = dialect.quote(writer_role)
    try:
        namespace = str(
            _first(connection.execute("SELECT current_schema()").fetchone())
        )
        namespace_q = dialect.quote(namespace)
        with connection.transaction():
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(current_schema() || ':' || %s))",
                (dialect.oplog_table(schema),),
            )
            connection.execute(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA "
                f"{namespace_q} GRANT {', '.join(REQUIRED_DML)} ON TABLES TO {writer}"
            )
            for table in dialect.schema_tables(schema):
                exists = connection.execute(
                    "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=current_schema() AND c.relname=%s AND c.relkind='r'",
                    (table,),
                ).fetchone()
                if exists is not None:
                    qualified = f"{namespace_q}.{dialect.quote(table)}"
                    connection.execute(f"ALTER TABLE {qualified} OWNER TO {owner}")
            connection.execute(f"SET LOCAL ROLE {owner}")
            for statement in dialect.create_sql(schema):
                connection.execute(statement)
            evolution = SchemaEvolution()
            evolution.dialect = dialect
            evolution.schema = schema
            evolution._connection = connection
            evolution._ensure_declared_fields_locked()
            for table, column, coltype, default in dialect.additive_columns(schema):
                exists = connection.execute(
                    "SELECT 1 FROM pg_attribute a "
                    "JOIN pg_class c ON c.oid=a.attrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=current_schema() AND c.relname=%s "
                    "AND a.attname=%s AND a.attnum>0 AND NOT a.attisdropped",
                    (table, column),
                ).fetchone()
                if exists is not None:
                    continue
                connection.execute(
                    dialect.add_column_sql(table, column, coltype, default)
                )
            tables = ", ".join(
                f"{namespace_q}.{dialect.quote(table)}"
                for table in dialect.schema_tables(schema)
            )
            connection.execute(
                f"GRANT {', '.join(REQUIRED_DML)} ON TABLE {tables} TO {writer}"
            )
        observed = _inspect(
            connection, schema, owner_role=owner_role, writer_role=writer_role
        )
        if not observed.ready:
            raise StoreProvisionError(
                "Store ACL provisioning committed but its independent catalogue "
                f"verification still reports drift: {observed!r}."
            )
        return observed
    except Exception as exc:
        if isinstance(exc, StoreProvisionError):
            raise
        raise StoreProvisionError(
            f"Could not provision Store {schema.name!r} as owner "
            f"{owner_role!r} with DML role {writer_role!r}: {exc}. "
            "Run this only through an authorized migration identity; never "
            "grant ownership to an application role."
        ) from exc
    finally:
        connection.close()


def requires_privileged_provisioning(connection: Any) -> bool:
    """Whether this database declares the managed owner/writer role contract."""
    found = {
        str(_first(row))
        for row in connection.execute(
            "SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s)",
            (DEFAULT_OWNER_ROLE, DEFAULT_WRITER_ROLE),
        ).fetchall()
    }
    return found == {DEFAULT_OWNER_ROLE, DEFAULT_WRITER_ROLE}


def managed_store_needs_provisioning(
    connection: Any,
    dialect: Any,
    schema: Schema,
    *,
    rows_exist: bool,
    schema_objects_missing: bool,
) -> bool:
    """Whether opening this managed Store would otherwise execute DDL."""
    if not requires_privileged_provisioning(connection):
        return False
    if schema_objects_missing or not rows_exist:
        return True
    rows_table = dialect.rows_table(schema)
    definitions = connection.execute(
        dialect.column_definitions_sql(rows_table)
    ).fetchall()
    physical_fields = {str(definition["column_name"]) for definition in definitions}
    if any(field not in physical_fields for field in schema.fields):
        return True
    for table, column, _coltype, _default in dialect.additive_columns(schema):
        columns = connection.execute(dialect.columns_sql(table)).fetchall()
        physical_columns = {str(_first(row)) for row in columns}
        if physical_columns and column not in physical_columns:
            return True
    return False


__all__ = [
    "DEFAULT_OWNER_ROLE",
    "DEFAULT_WRITER_ROLE",
    "REQUIRED_DML",
    "StoreAclStatus",
    "inspect_store_acl",
    "managed_store_needs_provisioning",
    "provision_store_acl",
    "requires_privileged_provisioning",
]

# EOF
