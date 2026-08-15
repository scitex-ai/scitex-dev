#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Record keys and the write guards.

Free functions rather than store methods, so each guard can be tested on
its own without a database. A guard that is only reachable through a live
connection tends to be tested once, through the happy path, and then
trusted forever.

The optimistic lock lives here. Its contract is three-valued and every
value is explicit at the call site:

* :data:`NEW_RECORD` — the record must NOT exist,
* an ``int`` — the record must exist at exactly that revision,
* :data:`ANY_REVISION` — write unconditionally, accepting lost-update risk.

There is no fourth "unspecified" case. A caller that has not thought about
concurrency is made to think about it once, at the point where the answer
is cheapest to supply.
"""

from __future__ import annotations

from typing import Any, Final, Mapping, Sequence

from ._errors import (
    RecordNotFoundError,
    RevisionMismatchError,
    StoreError,
    WriterConflictError,
)
from ._policy import Schema
from ._row import Row

__all__ = [
    "ANY_REVISION",
    "KEY_SEPARATOR",
    "NEW_RECORD",
    "check_owner",
    "check_revision",
    "record_key",
    "record_key_from",
]

#: Joins identity components into the flat record id. A unit separator,
#: because it cannot occur in an identifier a human typed — a comma or a
#: colon can, and would make ("a,b", "c") and ("a", "b,c") the same record.
KEY_SEPARATOR: Final[str] = "\x1f"


class _AnyRevision:
    """Sentinel type for :data:`ANY_REVISION`."""

    _instance: "_AnyRevision | None" = None

    def __new__(cls) -> "_AnyRevision":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "ANY_REVISION"


#: Opt out of the optimistic lock for one call. Explicit and greppable:
#: ``rg ANY_REVISION`` lists every place the fleet accepts lost-update risk,
#: which a boolean ``locked=False`` would not.
ANY_REVISION: Final[_AnyRevision] = _AnyRevision()

#: Assert the record does NOT yet exist. "Create" and "update" are separate
#: intents; the store makes the caller say which one it means rather than
#: inferring it from whether a row happens to be there.
NEW_RECORD: Final[None] = None


def record_key(schema: Schema, values: Mapping[str, Any]) -> str:
    """Derive the flat record id from a mapping of values."""
    missing = [n for n in schema.identity_fields if values.get(n) is None]
    if missing:
        raise StoreError(
            f"Store {schema.name!r}: write is missing IDENTITY value(s) "
            f"{missing}. Without them the record cannot be named, so the "
            "write has no target."
        )
    return KEY_SEPARATOR.join(str(values[n]) for n in schema.identity_fields)


def record_key_from(
    schema: Schema, key: "Mapping[str, Any] | Sequence[Any]"
) -> str:
    """Derive the record id from either a mapping or a positional key."""
    if isinstance(key, Mapping):
        return record_key(schema, key)
    if isinstance(key, str):
        # A bare string is a single-component key, not a sequence of chars.
        key = (key,)
    identity = schema.identity_fields
    if len(key) != len(identity):
        raise StoreError(
            f"Store {schema.name!r}: key {key!r} has {len(key)} component(s) "
            f"but the schema's identity is {identity} ({len(identity)}). "
            "Pass a mapping to avoid positional ambiguity."
        )
    return KEY_SEPARATOR.join(str(part) for part in key)


def check_revision(
    record: str,
    current: "Row | None",
    current_revision: int,
    expected: "int | None | _AnyRevision",
) -> None:
    """Enforce the optimistic lock, or raise saying exactly what to do."""
    if isinstance(expected, _AnyRevision):
        return

    if expected is NEW_RECORD:
        if current is not None:
            raise RevisionMismatchError(
                f"Record {record!r} already exists at revision "
                f"{current_revision}, but the write asserted NEW_RECORD. If "
                "an update was intended, re-read the record and pass its "
                "revision; if a create was intended, the id is taken."
            )
        return

    if current is None:
        raise RecordNotFoundError(
            f"Record {record!r} does not exist, but the write expected "
            f"revision {expected}. For a create, pass "
            "expected_revision=NEW_RECORD. If it was expected to exist: "
            "nothing deleted it — this store has no delete — so check the key."
        )

    if current_revision != expected:
        raise RevisionMismatchError(
            f"Record {record!r} is at revision {current_revision}, not the "
            f"expected {expected} — another writer changed it since you read "
            "it. Re-read, re-apply your intent to the new value, and retry. "
            "Do not retry with the same revision, and do not switch to "
            "ANY_REVISION to make this go away: that converts a DETECTED "
            "conflict into a SILENT lost update."
        )


def check_owner(schema: Schema, record: str, current: Row, actor: str) -> None:
    """Enforce single-writer ownership. Only called in that mode."""
    if current.owner != actor:
        raise WriterConflictError(
            f"Store {schema.name!r} runs under SINGLE_WRITER, and record "
            f"{record!r} is owned by {current.owner!r}, not {actor!r}. "
            "Ownership moves only through handover() called by the current "
            "owner. If records here are legitimately written by several "
            "parties — a board where anyone may comment, or where one party "
            "reassigns another's work — this store wants "
            "WriterPolicy.MULTI_WRITER instead."
        )

# EOF
