#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Full-text search, and the index it must agree with.

The one property here that nothing else can check: the GIN index and the
query's match expression are generated from a single declaration, and if
they ever differed the results would stay CORRECT while the index went
silently unused. The planner reports nothing, no test fails, and the only
symptom is that search got slow. So the index's existence is asserted
directly, on both sides — present when a schema declares searchable fields,
absent when it does not.

The query language is PostgreSQL's ``websearch_to_tsquery``, chosen because
the text arriving here was typed by a person: it ANDs bare words, honours
quoted phrases, reads ``or`` as a disjunction, and never raises on
malformed input. ``to_tsquery`` would reject an unbalanced quote with a
syntax error, turning a half-typed search box into a traceback.

Filters, ordering and counting live in ``test__query_search.py``; the
catalogue all of them assert on is declared once, in ``conftest``.
"""

from __future__ import annotations

import pytest

from scitex_dev.store import Query, SchemaError, eq


def _index_names(store, table: str) -> set:
    rows = store._connection.execute(
        "SELECT indexname FROM pg_indexes WHERE tablename = %s "
        "AND schemaname = current_schema()",
        (table,),
    ).fetchall()
    return {row["indexname"] for row in rows}


def test_full_text_matches_a_word_in_the_name(catalog):
    # Arrange
    query = Query().matching("alzheimer")

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 1


def test_full_text_matches_a_word_in_the_readme(catalog):
    """Two rows say 'memory' — one in its title, one in its body."""
    # Arrange
    query = Query().matching("memory")

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 2


def test_full_text_ands_bare_words(catalog):
    # Arrange
    query = Query().matching("memory hippocampal")

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 1


def test_full_text_reads_or_as_a_disjunction(catalog):
    # Arrange
    query = Query().matching("alzheimer or hippocampal")

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 2


def test_full_text_searches_a_json_field_too(catalog):
    """``modalities`` is a JSON list, and it is declared searchable."""
    # Arrange
    query = Query().matching("ephys")

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 1


def test_full_text_combines_with_a_structured_filter(catalog):
    """The whole point of putting search in the store rather than in the
    caller: the text criterion and the filters are ONE statement, so a
    limit applies to what actually matched rather than to a prefix of the
    table that is then narrowed in Python."""
    # Arrange
    query = Query().matching("memory").where(eq("source", "dandi"))

    # Act
    found = catalog.search(query)

    # Assert
    assert [row.values["id"] for row in found] == ["dandi:000003"]


def test_full_text_does_not_match_a_hidden_row(catalog):
    # Arrange
    query = Query().matching("withdrawn")

    # Act
    found = catalog.search(query)

    # Assert
    assert found == []


def test_full_text_finds_a_hidden_row_when_asked_to(catalog):
    """Hidden is not gone, and the search surface must not make it look so."""
    # Arrange
    query = Query().matching("withdrawn").with_hidden()

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 1


def test_full_text_survives_an_unbalanced_quote(catalog):
    """``to_tsquery`` raises on it; a half-typed search box must not become
    a traceback."""
    # Arrange
    query = Query().matching('"memory')

    # Act
    found = catalog.search(query)

    # Assert
    assert isinstance(found, list)


def test_a_word_nothing_holds_matches_nothing(catalog):
    """The positive control's partner: the searches above would look the
    same if the expression matched every row."""
    # Arrange
    query = Query().matching("thermodynamics")

    # Act
    found = catalog.search(query)

    # Assert
    assert found == []


def test_full_text_on_a_schema_that_declares_none_says_so(unsearchable):
    """An empty result would read as 'nothing matched'. It is not that."""
    # Arrange
    query = Query().matching("anything")
    # Act
    # Assert
    with pytest.raises(SchemaError, match="no searchable fields"):
        unsearchable.search(query)


def test_the_full_text_index_exists_on_the_rows_table(catalog):
    """Built from the same expression the query uses. Were it absent, every
    search would silently be a sequential scan and nothing would say so."""
    # Arrange
    expected = "catalog_rows_text_idx"

    # Act
    found = _index_names(catalog, "catalog_rows")

    # Assert
    assert expected in found


def test_no_full_text_index_where_no_field_is_searchable(unsearchable):
    # Arrange
    unwanted = "plain_rows_text_idx"

    # Act
    found = _index_names(unsearchable, "plain_rows")

    # Assert
    assert unwanted not in found


def test_reopening_a_store_does_not_fail_on_the_existing_index(
    open_store, catalog_schema
):
    """The index is created with IF NOT EXISTS, but on Postgres that clause
    checks ownership BEFORE it short-circuits — so the existence probe has
    to know about this index too, or a second open re-runs the DDL."""
    # Arrange
    first = open_store(catalog_schema, "reopened", key="reopened")

    # Act
    again = open_store(catalog_schema, "reopened", key="reopened")

    # Assert
    assert _index_names(again, "catalog_rows") == _index_names(first, "catalog_rows")

# EOF
