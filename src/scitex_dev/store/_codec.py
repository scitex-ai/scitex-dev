#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Value and row codec — the only place that knows the on-disk shape.

Split out of the store so that "how a value is stored" is one file rather
than a habit spread across every query. If a backend needs a different
representation for a kind, it changes here and nowhere else.

Two asymmetries are deliberate:

* JSON fields are serialised with ``sort_keys=True``. A stable byte form
  means two nodes that computed the same value produce the same bytes, so
  a diff, a hash or an eyeball comparison does not report a change that is
  only key ordering.
* Booleans round-trip through the dialect rather than Python's ``bool``.
  SQLite has no boolean type and stores 0/1; Postgres has a real one.
  Reading either back through ``from_db_bool`` is what keeps ``hidden``
  meaning the same thing on both.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from ._hlc import HLC
from ._policy import FieldKind, Schema
from ._row import Row

__all__ = ["RowCodec"]


class RowCodec:
    """Translates rows between Python and one backend's column values."""

    def __init__(self, schema: Schema, dialect: Any) -> None:
        self.schema = schema
        self.dialect = dialect

    # -- scalars ----------------------------------------------------------
    def encode_value(self, name: str, value: Any) -> Any:
        """Python value -> column value."""
        if value is None:
            return None
        kind = self.schema.fields[name].kind
        if kind is FieldKind.JSON:
            return json.dumps(value, sort_keys=True, default=str)
        if kind is FieldKind.BOOL:
            return self.dialect.to_db_bool(bool(value))
        return value

    def decode_value(self, name: str, value: Any) -> Any:
        """Column value -> Python value."""
        if value is None:
            return None
        kind = self.schema.fields[name].kind
        if kind is FieldKind.JSON:
            return json.loads(value) if isinstance(value, (str, bytes)) else value
        if kind is FieldKind.BOOL:
            return self.dialect.from_db_bool(value)
        return value

    # -- stamps -----------------------------------------------------------
    @staticmethod
    def encode_stamps(stamps: Mapping[str, HLC]) -> str:
        """Per-field HLC map -> the ``_field_hlc`` column."""
        return json.dumps(
            {name: stamp.encode() for name, stamp in stamps.items()}, sort_keys=True
        )

    @staticmethod
    def decode_stamps(text: str) -> dict[str, HLC]:
        """The ``_field_hlc`` column -> per-field HLC map."""
        return {name: HLC.decode(value) for name, value in json.loads(text).items()}

    # -- rows -------------------------------------------------------------
    def row_columns(self) -> list[str]:
        """Every column of the rows table, system columns first."""
        return [
            "_record",
            "_owner",
            "_origin",
            "_seq",
            "_revision",
            "_hlc",
            "_hidden",
            "_field_hlc",
            *self.schema.fields,
        ]

    def row_payload(self, record: str, row: Row, revision: int) -> tuple[Any, ...]:
        """A row -> the bind values for an upsert, ordered by :meth:`row_columns`."""
        return (
            record,
            row.owner,
            row.origin,
            row.seq,
            revision,
            row.hlc.encode(),
            self.dialect.to_db_bool(row.hidden),
            self.encode_stamps(row.field_hlc),
            *[self.encode_value(name, row.values.get(name)) for name in self.schema.fields],
        )

    def row_from_db(self, record: Mapping[str, Any]) -> Row:
        """A database row -> :class:`~._row.Row`."""
        values = {
            name: self.decode_value(name, record[name]) for name in self.schema.fields
        }
        return Row(
            key=tuple(values[name] for name in self.schema.identity_fields),
            values=values,
            owner=record["_owner"],
            origin=record["_origin"],
            hlc=HLC.decode(record["_hlc"]),
            hidden=self.dialect.from_db_bool(record["_hidden"]),
            seq=record["_seq"],
            field_hlc=self.decode_stamps(record["_field_hlc"]),
        )

# EOF
