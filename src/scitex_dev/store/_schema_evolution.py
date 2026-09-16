#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe, observed evolution of fields declared by a package schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._errors import SchemaEvolutionError
from ._policy import FieldRole, Schema

__all__ = ["SchemaEvolution", "SchemaEvolutionResult"]


@dataclass(frozen=True, slots=True)
class SchemaEvolutionResult:
    """The declared and physical fields observed while opening a store.

    ``added`` names fields this call physically created. ``existing`` names
    declared fields already present before the call. ``observed`` is a second
    catalogue read after all DDL and is the evidence behind success.
    """

    table: str
    added: tuple[str, ...]
    existing: tuple[str, ...]
    observed: tuple[str, ...]


class SchemaEvolution:
    """Mixin owning additive declared-field evolution and no record I/O."""

    dialect: Any
    schema: Schema
    _connection: Any

    def _ensure_declared_fields_locked(self) -> SchemaEvolutionResult:
        """Evolve missing fields while the database schema lock is held."""
        table = self.dialect.rows_table(self.schema)
        before_rows = self._connection.execute(
            self.dialect.column_definitions_sql(table)
        ).fetchall()
        if not before_rows:
            raise SchemaEvolutionError(
                f"Cannot evolve schema {self.schema.name!r}: physical table "
                f"{table!r} is absent. Open the Store through its declared "
                "target so schema creation runs before evolution."
            )
        before = {str(row["column_name"]): row for row in before_rows}
        existing: list[str] = []
        added: list[str] = []

        for name, policy in self.schema.fields.items():
            physical = before.get(name)
            if physical is not None:
                actual_kind = self.dialect.physical_kind(physical)
                if actual_kind is not policy.kind:
                    rendered = physical.get("udt_name", "unknown")
                    raise SchemaEvolutionError(
                        f"Cannot evolve schema {self.schema.name!r}: field "
                        f"{name!r} is declared {policy.kind.value} but physical "
                        f"column {table}.{name} is {rendered!r}. Retyping is "
                        "destructive; provide a reviewed migration."
                    )
                if (
                    policy.role is FieldRole.DATA
                    and not policy.required
                    and str(physical.get("is_nullable", "NO")) != "YES"
                ):
                    raise SchemaEvolutionError(
                        f"Cannot evolve schema {self.schema.name!r}: optional "
                        f"DATA field {name!r} is physically NOT NULL. The "
                        "declaration and deployed constraint disagree; repair "
                        "them with a reviewed migration."
                    )
                existing.append(name)
                continue

            if policy.role is not FieldRole.DATA or policy.required:
                raise SchemaEvolutionError(
                    f"Cannot add missing field {name!r} to schema "
                    f"{self.schema.name!r} automatically: additive evolution "
                    "accepts only DATA fields with required=False. Identity "
                    "and required fields need an explicit backfill migration."
                )
            self._connection.execute(
                self.dialect.add_nullable_column_sql(
                    table, name, self.dialect.column_type(policy.kind)
                )
            )
            added.append(name)

        after_rows = self._connection.execute(
            self.dialect.column_definitions_sql(table)
        ).fetchall()
        after = {str(row["column_name"]): row for row in after_rows}
        missing_after = [name for name in self.schema.fields if name not in after]
        if missing_after:
            raise SchemaEvolutionError(
                f"Schema evolution for {self.schema.name!r} did not materialise "
                f"declared field(s) {missing_after} in {table!r}. The physical "
                "post-observation refused readiness."
            )
        for name, policy in self.schema.fields.items():
            physical = after[name]
            if self.dialect.physical_kind(physical) is not policy.kind:
                raise SchemaEvolutionError(
                    f"Schema evolution for {self.schema.name!r} observed an "
                    f"incompatible physical type for {table}.{name} after DDL."
                )
            if name in added and str(physical.get("is_nullable", "NO")) != "YES":
                raise SchemaEvolutionError(
                    f"Schema evolution for {self.schema.name!r} added {name!r} "
                    "but physical post-observation says it is not nullable."
                )

        return SchemaEvolutionResult(
            table=table,
            added=tuple(added),
            existing=tuple(existing),
            observed=tuple(name for name in self.schema.fields if name in after),
        )
