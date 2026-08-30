#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turning a :class:`~._query.Query` into one statement, for one dialect.

Split from :mod:`._query` because the two answer different questions and
change for different reasons. ``_query`` is the VOCABULARY a caller writes
in — it has no idea a database exists. This module is the only place that
knows a query becomes SQL, and even here every engine-specific fragment
(quoting, placeholder style, the full-text expression, JSON containment) is
asked of the dialect rather than written out.

TWO INVARIANTS THIS FILE ENFORCES, both of which have a failure attached.

**Identifiers come from the SCHEMA; values are bound.** Nothing a caller
types reaches an identifier position. A field name is looked up in the
schema and rejected if absent, so the worst a bad name can do is raise —
never select a column that was not meant to be selectable, and never
smuggle an expression into a WHERE clause.

**Every ordering is total.** A ``LIMIT``/``OFFSET`` over a non-total order
is a paging bug that only appears once two rows tie: the engine may return
them in either order per statement, so page 1 and page 2 can show one row
twice and skip another. The record key is appended to every ORDER BY as a
final tie-break, which costs nothing and makes paging deterministic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

from ._errors import SchemaError
from ._policy import FieldKind, Schema
from ._query import COMPARISONS, Condition, Either, Op, ORDERING_OPS, Query

__all__ = [
    "Compiled",
    "QueryCompiler",
    "compile_count",
    "compile_select",
    "compile_tally",
]

#: Kinds for which "greater" is meaningful. Mirrors :mod:`._policy`'s list
#: for ``MergeRule.MAX``; both answer the same question about the same kinds.
_ORDERABLE_KINDS: Final[frozenset[FieldKind]] = frozenset(
    {FieldKind.INTEGER, FieldKind.REAL, FieldKind.TEXT}
)


@dataclass(frozen=True, slots=True)
class Compiled:
    """A rendered statement and its bind values, in the driver's order."""

    sql: str
    params: tuple[Any, ...]


def check_field(schema: Schema, name: str) -> None:
    """Refuse a field the schema does not declare."""
    if name not in schema.fields:
        raise SchemaError(
            f"Query names field {name!r}, which schema {schema.name!r} does "
            f"not declare. Known fields: {sorted(schema.fields)}. A query "
            "cannot name a column the schema has no policy for — that is how "
            "a typo becomes an empty result set with nothing to explain it."
        )


def check_condition(schema: Schema, condition: Condition) -> None:
    """Refuse a condition whose operator does not fit its field's kind."""
    check_field(schema, condition.field)
    kind = schema.fields[condition.field].kind
    if condition.op is Op.CONTAINS and kind is not FieldKind.JSON:
        raise SchemaError(
            f"contains({condition.field!r}, ...) needs a JSON field, but "
            f"{condition.field!r} is {kind.value}. Containment is a question "
            "about a document; on a scalar it would have to become a "
            "substring match, which is a different question wearing the "
            "same name."
        )
    if condition.op in ORDERING_OPS and kind not in _ORDERABLE_KINDS:
        raise SchemaError(
            f"{condition.op.value}({condition.field!r}, ...) needs an "
            f"orderable kind {sorted(k.value for k in _ORDERABLE_KINDS)}, "
            f"but {condition.field!r} is {kind.value}."
        )
    if condition.op is Op.NONEMPTY and kind is not FieldKind.TEXT:
        raise SchemaError(
            f"nonempty({condition.field!r}) needs a text field, but "
            f"{condition.field!r} is {kind.value}. 'Not the empty string' "
            "has no meaning for it."
        )


class QueryCompiler:
    """Renders one query for one dialect.

    Constructed per statement rather than held on the store: it carries the
    running placeholder index, which is per-statement state, and a shared
    instance would hand two concurrent callers each other's parameters.
    """

    def __init__(self, schema: Schema, dialect: Any, codec: Any) -> None:
        self.schema = schema
        self.dialect = dialect
        self.codec = codec
        self._params: list[Any] = []

    # -- helpers ----------------------------------------------------------
    def _bind(self, value: Any) -> str:
        """Record a bind value and return its placeholder."""
        index = len(self._params)
        self._params.append(value)
        return self.dialect.placeholder(index)

    def _column(self, name: str) -> str:
        return self.dialect.quote(name)

    # -- fragments --------------------------------------------------------
    def _condition_sql(self, condition: Condition) -> str:
        check_condition(self.schema, condition)
        column = self._column(condition.field)
        op = condition.op

        if op is Op.IS_NULL:
            return f"{column} IS NULL"
        if op is Op.NONEMPTY:
            return f"({column} IS NOT NULL AND {column} <> {self._bind('')})"
        if op is Op.CONTAINS:
            return self.dialect.json_contains_sql(
                column, self._bind(json.dumps(condition.value, sort_keys=True))
            )
        if op is Op.IN:
            values = tuple(condition.value)
            if not values:
                # An empty IN list is legal to ASK and impossible to satisfy.
                # `IN ()` is a syntax error, so say the same thing in a form
                # the parser accepts rather than raising on a caller whose
                # filter list legitimately came back empty.
                return "FALSE"
            rendered = ", ".join(
                self._bind(self.codec.encode_value(condition.field, value))
                for value in values
            )
            return f"{column} IN ({rendered})"

        encoded = self.codec.encode_value(condition.field, condition.value)
        return f"{column} {COMPARISONS[op]} {self._bind(encoded)}"

    def _predicate_sql(self, predicate: Any) -> str:
        if isinstance(predicate, Either):
            parts = [self._condition_sql(option) for option in predicate.options]
            return "(" + " OR ".join(parts) + ")"
        return self._condition_sql(predicate)

    def _text_sql(self, text: str) -> str:
        if not self.schema.text_search:
            raise SchemaError(
                f"Schema {self.schema.name!r} declares no searchable fields, "
                "so there is nothing for a full-text query to match. Declare "
                "them once, where the index is built from the same list: "
                'Schema.build(name, fields, text_search=("title", "body")).'
            )
        return self.dialect.text_match_sql(self.schema, self._bind(text))

    def _where_sql(self, query: Query) -> str:
        clauses: list[str] = []
        if not query.include_hidden:
            clauses.append(
                f"{self._column('_hidden')} = "
                f"{self._bind(self.dialect.to_db_bool(False))}"
            )
        if query.text:
            clauses.append(self._text_sql(query.text))
        clauses.extend(self._predicate_sql(p) for p in query.predicates)
        return " AND ".join(clauses) if clauses else "TRUE"

    def _order_sql(self, query: Query) -> str:
        parts = []
        for item in query.order:
            check_field(self.schema, item.field)
            direction = "DESC" if item.descending else "ASC"
            # NULLS LAST in both directions — see Order's docstring.
            parts.append(f"{self._column(item.field)} {direction} NULLS LAST")
        parts.append(f"{self._column('_record')} ASC")
        return " ORDER BY " + ", ".join(parts)

    # -- statements -------------------------------------------------------
    def select(self, query: Query, table: str) -> Compiled:
        """``SELECT *`` matching ``query``, ordered and paged."""
        sql = (
            f"SELECT * FROM {self.dialect.quote(table)} "
            f"WHERE {self._where_sql(query)}{self._order_sql(query)}"
        )
        if query.limit is not None:
            sql += f" LIMIT {self._bind(int(query.limit))}"
        if query.offset:
            sql += f" OFFSET {self._bind(int(query.offset))}"
        return Compiled(sql, tuple(self._params))

    def count(self, query: Query, table: str) -> Compiled:
        """``SELECT COUNT(*)`` matching ``query``. Order and paging ignored."""
        sql = (
            f"SELECT COUNT(*) AS n FROM {self.dialect.quote(table)} "
            f"WHERE {self._where_sql(query)}"
        )
        return Compiled(sql, tuple(self._params))

    def tally(self, query: Query, table: str, group: str) -> Compiled:
        """``SELECT <group>, COUNT(*) ... GROUP BY <group>``."""
        check_field(self.schema, group)
        column = self._column(group)
        sql = (
            f"SELECT {column} AS bucket, COUNT(*) AS n FROM "
            f"{self.dialect.quote(table)} WHERE {self._where_sql(query)} "
            f"GROUP BY {column}"
        )
        return Compiled(sql, tuple(self._params))


def compile_select(
    query: Query, schema: Schema, dialect: Any, codec: Any, table: str
) -> Compiled:
    """Render ``query`` as a row SELECT. See :class:`QueryCompiler`."""
    return QueryCompiler(schema, dialect, codec).select(query, table)


def compile_count(
    query: Query, schema: Schema, dialect: Any, codec: Any, table: str
) -> Compiled:
    """Render ``query`` as a COUNT. See :class:`QueryCompiler`."""
    return QueryCompiler(schema, dialect, codec).count(query, table)


def compile_tally(
    query: Query, schema: Schema, dialect: Any, codec: Any, table: str, group: str
) -> Compiled:
    """Render ``query`` as a grouped COUNT. See :class:`QueryCompiler`."""
    return QueryCompiler(schema, dialect, codec).tally(query, table, group)

# EOF
