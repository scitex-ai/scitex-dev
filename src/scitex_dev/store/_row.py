#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``Row`` — the record type that crosses the store boundary.

A row is never a bare dict. It carries, alongside the caller's values, the
things every replication decision needs and that a dict would lose:

* ``owner`` — the record's DOMAIN owner (an assignee, a host). Mutable,
  and under ``MULTI_WRITER`` it may be changed by somebody other than the
  owner. It is not the replication key.
* ``origin`` / ``seq`` — which node accepted the op that last touched this
  row, and its sequence number there. This IS the replication coordinate.
* ``hlc`` — the record's hybrid-logical stamp,
* ``field_hlc`` — per-field stamps, so two nodes touching *different*
  fields of the same record both keep their change,
* ``hidden`` — the soft-delete marker, because nothing is ever deleted.

``hidden`` is a real field rather than an absence. "Row missing" and "row
hidden" are different answers and the caller must be able to tell them
apart; collapsing the second into the first is how a hide becomes
indistinguishable from a delete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._errors import SchemaError
from ._hlc import HLC
from ._policy import FieldRole, Schema

__all__ = ["Row"]


@dataclass(frozen=True, slots=True)
class Row:
    """One record, as read from or written to a store."""

    key: tuple[Any, ...]
    values: Mapping[str, Any]
    owner: str
    origin: str
    hlc: HLC
    hidden: bool
    seq: "int | None" = None
    field_hlc: Mapping[str, HLC] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key:
            raise SchemaError(
                "Row.key is empty. Every row is keyed by its schema's "
                "IDENTITY fields; an empty key cannot be owned or replayed."
            )
        if not self.owner:
            raise SchemaError(
                "Row.owner is empty. Even under MULTI_WRITER a record records "
                "who it belongs to — that is domain information the board "
                "displays, not only a replication concern."
            )
        if not self.origin:
            raise SchemaError(
                "Row.origin is empty. It names the node that accepted the op "
                "producing this row and is the coordinate replay is keyed by."
            )

    # -- construction -----------------------------------------------------
    @classmethod
    def from_values(
        cls,
        schema: Schema,
        values: Mapping[str, Any],
        *,
        writer: str,
        hlc: HLC,
        seq: "int | None" = None,
        field_hlc: "Mapping[str, HLC] | None" = None,
    ) -> "Row":
        """Build a row against ``schema``, validating identity and required.

        The hide flag is read from ``values`` when the schema declares one,
        so callers never pass ``hidden`` separately and the two can never
        disagree.
        """
        missing_identity = [
            name for name in schema.identity_fields if values.get(name) is None
        ]
        if missing_identity:
            raise SchemaError(
                f"Schema {schema.name!r}: row is missing IDENTITY value(s) "
                f"{missing_identity}. Identity fields are the record key and "
                "cannot be NULL."
            )

        missing_required = [
            name
            for name, policy in schema.fields.items()
            if policy.required and values.get(name) is None
        ]
        if missing_required:
            raise SchemaError(
                f"Schema {schema.name!r}: row is missing required value(s) "
                f"{missing_required}. Either supply them or set "
                "required=False in their FieldPolicy."
            )

        unknown = [name for name in values if name not in schema.fields]
        if unknown:
            raise SchemaError(
                f"Schema {schema.name!r}: row carries column(s) {unknown} "
                f"with no FieldPolicy. Known fields: {sorted(schema.fields)}. "
                "Add them to the schema — an untyped column has no merge rule "
                "and could not be reconciled."
            )

        hide_field = schema.hide_flag_field
        hidden = bool(values.get(hide_field, False)) if hide_field else False

        return cls(
            key=tuple(values[name] for name in schema.identity_fields),
            values=dict(values),
            writer=writer,
            hlc=hlc,
            hidden=hidden,
            seq=seq,
            field_hlc=dict(field_hlc or {}),
        )

    # -- views ------------------------------------------------------------
    def key_text(self, schema: Schema) -> str:
        """A stable text form of the key, used as the oplog's record id."""
        return "\x1f".join(
            str(self.values[name]) for name in schema.identity_fields
        )

    def data(self, schema: Schema) -> dict[str, Any]:
        """The non-identity values only."""
        return {
            name: value
            for name, value in self.values.items()
            if schema.fields[name].role is not FieldRole.IDENTITY
        }

    def with_values(self, **changes: Any) -> "Row":
        """A copy with ``changes`` applied to ``values``.

        Does not re-stamp the clock — the store does that when the change is
        appended to the oplog, so a stamp always corresponds to a real op.
        """
        merged = dict(self.values)
        merged.update(changes)
        return Row(
            key=self.key,
            values=merged,
            writer=self.writer,
            hlc=self.hlc,
            hidden=self.hidden,
            seq=self.seq,
            field_hlc=dict(self.field_hlc),
        )

# EOF
