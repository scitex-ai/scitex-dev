#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reading a store by CRITERIA rather than by key — the vocabulary.

The read door was :meth:`~._store.Store.get` (one record, by key) and
:meth:`~._store.Store.rows` (every record). Nothing in between. A consumer
that wanted "the fifty most-downloaded EEG datasets mentioning alzheimer"
had to pull the whole table into Python and filter it there — which is
exactly the moment a leaf package stops using the primitive and starts
re-implementing one.

WHY THIS IS HERE AND NOT IN THE CONSUMER. scitex-dataset kept a private
full-text index of its catalogue because this module did not exist. That
index was a second storage engine, a second schema and a second place for
the fleet's data to live — the shape ADR-0006 exists to end. The ABSENCE of
a search surface is what made the private index look reasonable. So the
surface belongs here, once, rather than in each package that discovers it
needs one.

WHAT A QUERY IS
---------------
A :class:`Query` is an immutable description of a question. It names fields,
never SQL, and every field it names is checked against the schema before a
statement is built — so a typo is a :class:`~._errors.SchemaError` at compile
time rather than a silent empty result, and no caller-supplied string ever
reaches an identifier position. Values travel as bind parameters.

::

    from scitex_dev.store import Query, eq, gte

    hits = store.search(
        Query()
        .matching("alzheimer eeg")
        .where(eq("source", "openneuro"), gte("n_subjects", 20))
        .ordered_by("downloads")
        .limited(50)
    )

FULL TEXT
---------
``matching`` searches the fields the SCHEMA declares searchable
(``Schema.build(..., text_search=(...))``), not fields named at the call
site. One declaration, so the index the store creates and the expression the
query builds are generated from the same list and cannot drift apart — an
expression index that does not match its query is an index that is silently
never used, and nothing fails to say so.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
No joins, no subqueries, no arbitrary expressions, no raw-SQL escape hatch.
This is a filter over one schema's rows. A consumer needing more than that
needs a different tool, and half a query language here would only make the
half-way point comfortable enough to stay in.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Final, Iterable

from ._errors import SchemaError

__all__ = [
    "Condition",
    "Either",
    "Op",
    "Order",
    "Query",
    "contains",
    "either",
    "eq",
    "gt",
    "gte",
    "is_in",
    "is_null",
    "lt",
    "lte",
    "ne",
    "nonempty",
]


class Op(str, Enum):
    """How one field is compared against one value.

    A closed set on purpose. Every member is something a rows table can
    answer, and nothing here can express a join or a correlated subquery —
    see the module docstring for why that ceiling is deliberate.
    """

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    #: Membership in a caller-supplied collection.
    IN = "in"
    #: JSON containment: the stored document CONTAINS the given value. On a
    #: JSON array field this asks "is this element present", which is the
    #: question a substring match on the serialised form only approximates.
    CONTAINS = "contains"
    #: Present AND not the empty string. ``IS NOT NULL`` alone is the check
    #: people write and it is the wrong one: a fetcher that stores an empty
    #: readme satisfies it, and "has a readme" then means "has the column".
    NONEMPTY = "nonempty"
    #: NULL. Kept separate from ``EQ(None)`` because SQL's ``= NULL`` is not
    #: false, it is unknown, and a caller who writes the former and means
    #: the latter gets an empty result with nothing to explain it.
    IS_NULL = "is_null"


#: Operators that take no value. Passing one is an error rather than an
#: ignored argument: a value that is silently dropped reads, to whoever
#: wrote it, exactly like a filter that is being applied.
VALUELESS_OPS: Final[frozenset[Op]] = frozenset({Op.NONEMPTY, Op.IS_NULL})

#: Operators requiring an ordering on the column's kind.
ORDERING_OPS: Final[frozenset[Op]] = frozenset({Op.GT, Op.GTE, Op.LT, Op.LTE})

#: The SQL symbol for each scalar comparison.
COMPARISONS: Final[dict[Op, str]] = {
    Op.EQ: "=",
    Op.NE: "<>",
    Op.GT: ">",
    Op.GTE: ">=",
    Op.LT: "<",
    Op.LTE: "<=",
}


@dataclass(frozen=True, slots=True)
class Condition:
    """One field, one operator, one value."""

    field: str
    op: Op
    value: Any = None

    def __post_init__(self) -> None:
        if self.op in VALUELESS_OPS and self.value is not None:
            raise SchemaError(
                f"Condition {self.field!r} {self.op.value} takes no value, "
                f"but {self.value!r} was given. It would be ignored, and an "
                "ignored filter reads exactly like an applied one."
            )
        if self.op is Op.IN and not isinstance(
            self.value, (list, tuple, set, frozenset)
        ):
            raise SchemaError(
                f"Condition {self.field!r} IN needs a collection, got "
                f"{type(self.value).__name__}. A bare string would be read "
                "as a collection of characters."
            )


@dataclass(frozen=True, slots=True)
class Either:
    """A disjunction: at least one of ``options`` must hold.

    The only nesting this query language has. Consumers reach for it when a
    single user-facing filter spans two columns — scitex-dataset's
    ``modality`` matches either the modality LIST or the single PRIMARY
    modality — and without it that filter has to be applied in Python after
    the fact, which defeats the limit and the ordering.
    """

    options: tuple[Condition, ...]

    def __post_init__(self) -> None:
        if not self.options:
            raise SchemaError(
                "Either(...) with no options can never hold, so it would "
                "silently reduce every result set to nothing. State the "
                "conditions, or drop the disjunction."
            )


@dataclass(frozen=True, slots=True)
class Order:
    """One sort key.

    ``NULLS LAST`` is not an option and not a parameter: nulls sort last in
    BOTH directions, always. PostgreSQL's default puts them FIRST under
    ``DESC``, so "the most downloaded datasets" would lead with every row
    whose download count was never recorded. Whatever an ordering is for,
    the rows that have no value for it are not the answer.
    """

    field: str
    descending: bool = True


@dataclass(frozen=True, slots=True)
class Query:
    """An immutable description of which rows to return, and in what order.

    Build with the fluent methods; each returns a NEW query. Nothing here
    executes anything — pass it to :meth:`~._store.Store.search`,
    :meth:`~._store.Store.count` or :meth:`~._store.Store.tally`.
    """

    text: "str | None" = None
    predicates: tuple[Any, ...] = ()
    order: tuple[Order, ...] = ()
    limit: "int | None" = None
    offset: int = 0
    include_hidden: bool = False

    # -- fluent construction ----------------------------------------------
    def matching(self, text: "str | None") -> "Query":
        """Full-text search over the schema's declared searchable fields.

        ``None`` or a blank string CLEARS the text criterion rather than
        matching nothing, so a caller can pass an optional search box
        straight through without branching on it.
        """
        cleaned = (text or "").strip()
        return replace(self, text=cleaned or None)

    def where(self, *predicates: Any) -> "Query":
        """Add conditions, ANDed with whatever is already there."""
        for predicate in predicates:
            if not isinstance(predicate, (Condition, Either)):
                raise SchemaError(
                    "Query.where takes Condition or Either, got "
                    f"{type(predicate).__name__}. Build one with eq(), "
                    "gte(), contains(), either() and friends."
                )
        return replace(self, predicates=(*self.predicates, *predicates))

    def ordered_by(self, field_name: str, *, descending: bool = True) -> "Query":
        """Append a sort key. Earlier keys take precedence."""
        return replace(self, order=(*self.order, Order(field_name, descending)))

    def limited(self, limit: "int | None", *, offset: int = 0) -> "Query":
        """Cap the result set, optionally skipping the first ``offset`` rows."""
        if limit is not None and limit < 0:
            raise SchemaError(f"Query limit must not be negative, got {limit}.")
        if offset < 0:
            raise SchemaError(f"Query offset must not be negative, got {offset}.")
        return replace(self, limit=limit, offset=offset)

    def with_hidden(self) -> "Query":
        """Include soft-deleted rows, which are excluded by default."""
        return replace(self, include_hidden=True)

    # -- introspection ----------------------------------------------------
    def named_fields(self) -> tuple[str, ...]:
        """Every schema field this query names, deduplicated."""
        named: list[str] = [item.field for item in self.order]
        for predicate in self.predicates:
            if isinstance(predicate, Either):
                named.extend(option.field for option in predicate.options)
            else:
                named.append(predicate.field)
        return tuple(dict.fromkeys(named))


# -- condition constructors -----------------------------------------------
#
# Functions rather than classmethods so a query reads as the sentence it is:
# ``where(eq("source", "dandi"), gte("n_subjects", 20))``.


def eq(field_name: str, value: Any) -> Condition:
    """``field == value``."""
    return Condition(field_name, Op.EQ, value)


def ne(field_name: str, value: Any) -> Condition:
    """``field != value``."""
    return Condition(field_name, Op.NE, value)


def gt(field_name: str, value: Any) -> Condition:
    """``field > value``."""
    return Condition(field_name, Op.GT, value)


def gte(field_name: str, value: Any) -> Condition:
    """``field >= value``."""
    return Condition(field_name, Op.GTE, value)


def lt(field_name: str, value: Any) -> Condition:
    """``field < value``."""
    return Condition(field_name, Op.LT, value)


def lte(field_name: str, value: Any) -> Condition:
    """``field <= value``."""
    return Condition(field_name, Op.LTE, value)


def is_in(field_name: str, values: Iterable[Any]) -> Condition:
    """``field`` is one of ``values``.

    The type check is HERE rather than only in :class:`Condition`, because
    ``tuple(values)`` would already have turned a bare string into a tuple
    of characters by the time the condition saw it — and ``is_in("source",
    "dandi")`` would then quietly mean "source is one of d, a, n, i".
    """
    if isinstance(values, (str, bytes)):
        raise SchemaError(
            f"is_in({field_name!r}, ...) needs a collection, got "
            f"{type(values).__name__}. A bare string is iterable, so this "
            "would silently become a set of its characters."
        )
    return Condition(field_name, Op.IN, tuple(values))


def contains(field_name: str, value: Any) -> Condition:
    """A JSON field CONTAINS ``value`` — an array element, or a sub-object.

    Real containment, not a substring match on the serialised text. Asking
    whether ``["mri", "eeg"]`` contains ``"eeg"`` this way cannot also be
    satisfied by a dataset whose free-text description happens to say
    ``eeg``, which is what the ``LIKE '%"eeg"%'`` idiom it replaces did.
    """
    return Condition(field_name, Op.CONTAINS, value)


def nonempty(field_name: str) -> Condition:
    """``field`` is present and not the empty string."""
    return Condition(field_name, Op.NONEMPTY)


def is_null(field_name: str) -> Condition:
    """``field`` is NULL."""
    return Condition(field_name, Op.IS_NULL)


def either(*options: Condition) -> Either:
    """At least one of ``options`` holds."""
    return Either(tuple(options))

# EOF
