#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Applying one op to one record — the materialisation step.

This is the function directed replay and the local write path SHARE. That
sharing is the point, not an economy: a locally-written op and a replayed
remote op must produce byte-identical state, or two replicas diverge while
both believe they are converged. Two code paths doing "the same" merge is
exactly how that divergence gets in, so there is one.

:func:`apply_entry` is pure with respect to the database — it takes the
current row and returns the next one. Persisting the result is the store's
job. That keeps the merge logic testable without a connection and makes it
obvious that applying an op cannot remove a row: the function has no way to
express that outcome. Its return type is a row, not an optional one.
"""

from __future__ import annotations

from typing import Any, Mapping

from ._hlc import HLC
from ._merge import MergeConflict, merge_field
from ._oplog import OpEntry, OpKind
from ._policy import Schema
from ._row import Row

__all__ = ["ApplyResult", "apply_entry"]


class ApplyResult(tuple):
    """``(row, conflicts)`` with names, so call sites read as intent.

    A plain tuple would work; the names stop ``result[1]`` appearing three
    modules away where nobody remembers what index 1 was.
    """

    __slots__ = ()

    def __new__(cls, row: Row, conflicts: "list[MergeConflict]") -> "ApplyResult":
        return super().__new__(cls, (row, conflicts))

    @property
    def row(self) -> Row:
        return self[0]

    @property
    def conflicts(self) -> "list[MergeConflict]":
        return self[1]


def apply_entry(
    schema: Schema,
    entry: OpEntry,
    current: "Row | None",
    *,
    owner: "str | None" = None,
    default_owner: str,
) -> ApplyResult:
    """Fold ``entry`` into ``current`` and return the resulting row.

    ``current`` is ``None`` for a record's first op. ``owner`` overrides the
    resulting row's domain owner (used on insert and hand-over);
    ``default_owner`` is the fallback when the record is new and no owner
    was given.
    """
    conflicts: list[MergeConflict] = []
    values: dict[str, Any] = dict(current.values) if current else {}
    stamps: dict[str, HLC] = dict(current.field_hlc) if current else {}
    hidden = current.hidden if current else False
    resolved_owner = owner or (current.owner if current else default_owner)

    if entry.op is OpKind.UPSERT:
        _apply_upsert(schema, entry, values, stamps, conflicts)
        hide_field = schema.hide_flag_field
        if hide_field and hide_field in entry.payload:
            hidden = bool(values.get(hide_field, False))
    elif entry.op is OpKind.HIDE:
        hidden = True
        _stamp_hide_flag(schema, entry, values, stamps, True)
    elif entry.op is OpKind.UNHIDE:
        hidden = False
        _stamp_hide_flag(schema, entry, values, stamps, False)
    elif entry.op is OpKind.HANDOVER:
        resolved_owner = entry.payload["to"]

    row = Row(
        key=tuple(values[name] for name in schema.identity_fields),
        values=values,
        owner=resolved_owner,
        origin=entry.origin,
        hlc=entry.hlc,
        hidden=hidden,
        seq=entry.seq,
        field_hlc=stamps,
    )
    return ApplyResult(row, conflicts)


def _apply_upsert(
    schema: Schema,
    entry: OpEntry,
    values: dict[str, Any],
    stamps: dict[str, HLC],
    conflicts: "list[MergeConflict]",
) -> None:
    """Merge each field in the payload according to its own policy.

    Field by field, never row by row. Merging whole rows is what makes two
    nodes editing different fields clobber each other; the per-field stamp
    is what lets both survive.
    """
    for name, incoming in entry.payload.items():
        policy = schema.policy(name)
        outcome = merge_field(
            name,
            policy,
            current=values.get(name),
            current_stamp=stamps.get(name),
            incoming=incoming,
            incoming_stamp=entry.hlc,
        )
        if outcome.conflict is not None:
            conflicts.append(outcome.conflict)
        values[name] = outcome.value
        stamps[name] = outcome.stamp


def _stamp_hide_flag(
    schema: Schema,
    entry: OpEntry,
    values: dict[str, Any],
    stamps: dict[str, HLC],
    hidden: bool,
) -> None:
    """Mirror a HIDE/UNHIDE op into the schema's hide-flag column, if any.

    A schema without a hide-flag field still hides — the ``_hidden`` system
    column carries it. The declared field exists so a consumer can query
    and index the flag like any other, not because hiding depends on it.
    """
    field = schema.hide_flag_field
    if field is None:
        return
    values[field] = hidden
    stamps[field] = entry.hlc


def payload_of(entry: OpEntry) -> Mapping[str, Any]:
    """The op's payload. Exists so callers do not reach into the dataclass."""
    return entry.payload

# EOF
