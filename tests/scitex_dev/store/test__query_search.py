#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Filtering, ordering, paging and counting, against the real engine.

These questions are about what PostgreSQL DOES, not about what the query
builder describes, and a fake would answer them the way the author expected
rather than the way the server does:

* ``NULLS LAST`` in both directions — the default is ``NULLS FIRST`` under
  ``DESC``, so "the most downloaded" would lead with every row whose count
  was never recorded.
* JSON containment meaning containment, rather than the ``LIKE '%"eeg"%'``
  approximation it replaces.
* An empty ``IN`` list, which is legal to ask and a syntax error to render.

Full text and its index live in ``test__query_text.py``; the checks that
need no database at all live in ``test__query_vocabulary.py``. The
catalogue every one of them asserts on is declared once, in ``conftest``.
"""

from __future__ import annotations

import pytest

from scitex_dev.store import (
    Query,
    SchemaError,
    contains,
    either,
    eq,
    gte,
    is_in,
    lte,
    nonempty,
)


# -- the default view -----------------------------------------------------
def test_search_without_criteria_returns_the_visible_rows(catalog):
    """A criterion-free query is ``rows()`` with a deterministic order."""
    # Arrange
    query = Query()

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 3


def test_search_excludes_hidden_rows_by_default(catalog):
    """Nothing is ever deleted, so the default view is the only thing
    between a caller and every record the store has ever held."""
    # Arrange
    query = Query()

    # Act
    ids = {row.values["id"] for row in catalog.search(query)}

    # Assert
    assert "dandi:000004" not in ids


def test_search_with_hidden_includes_them(catalog):
    # Arrange
    query = Query().with_hidden()

    # Act
    ids = {row.values["id"] for row in catalog.search(query)}

    # Assert
    assert "dandi:000004" in ids


# -- filters --------------------------------------------------------------
def test_search_filters_on_equality(catalog):
    # Arrange
    query = Query().where(eq("source", "openneuro"))

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 2


def test_search_filters_on_a_lower_bound(catalog):
    # Arrange
    query = Query().where(gte("n_subjects", 30))

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 2


def test_search_filters_on_a_closed_range(catalog):
    # Arrange
    query = Query().where(gte("n_subjects", 20), lte("n_subjects", 40))

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 1


def test_search_filters_on_membership(catalog):
    # Arrange
    query = Query().where(is_in("source", ("dandi", "physionet")))

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 1


def test_membership_in_an_empty_collection_matches_nothing(catalog):
    """``IN ()`` is a syntax error; a filter list that came back empty is
    not, and must not take the caller down with it."""
    # Arrange
    query = Query().where(is_in("source", ()))

    # Act
    found = catalog.search(query)

    # Assert
    assert found == []


def test_search_filters_on_json_containment(catalog):
    # Arrange
    query = Query().where(contains("modalities", "eeg"))

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 1


def test_json_containment_asks_about_the_list_not_the_prose(catalog):
    """Only the two rows whose MODALITY list holds ``mri`` — not any row
    that merely mentions it, which the serialised-substring idiom this
    replaces could not tell apart."""
    # Arrange
    query = Query().where(contains("modalities", "mri"))

    # Act
    ids = {row.values["id"] for row in catalog.search(query)}

    # Assert
    assert ids == {"openneuro:ds001", "openneuro:ds002"}


def test_nonempty_rejects_the_empty_string(catalog):
    """``IS NOT NULL`` alone accepts it, and 'has a readme' then means
    'has the column'."""
    # Arrange
    query = Query().where(nonempty("readme"))

    # Act
    ids = {row.values["id"] for row in catalog.search(query)}

    # Assert
    assert "openneuro:ds002" not in ids


def test_either_matches_across_two_columns(catalog):
    # Arrange
    query = Query().where(either(eq("source", "dandi"), eq("n_subjects", 10)))

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 2


# -- ordering and paging --------------------------------------------------
def test_ordering_descending_puts_the_largest_first(catalog):
    # Arrange
    query = Query().ordered_by("downloads")

    # Act
    found = catalog.search(query)

    # Assert
    assert found[0].values["downloads"] == 500


def test_ordering_descending_puts_nulls_last(catalog):
    """Postgres defaults to NULLS FIRST under DESC, which would lead 'the
    most downloaded' with every row whose count was never recorded."""
    # Arrange
    query = Query().ordered_by("downloads")

    # Act
    found = catalog.search(query)

    # Assert
    assert found[-1].values["downloads"] is None


def test_ordering_ascending_also_puts_nulls_last(catalog):
    # Arrange
    query = Query().ordered_by("downloads", descending=False)

    # Act
    found = catalog.search(query)

    # Assert
    assert found[-1].values["downloads"] is None


def test_limit_caps_the_result_set(catalog):
    # Arrange
    query = Query().ordered_by("n_subjects").limited(2)

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 2


def test_offset_skips_the_first_page(catalog):
    # Arrange
    query = Query().ordered_by("n_subjects").limited(2, offset=2)

    # Act
    found = catalog.search(query)

    # Assert
    assert len(found) == 1


def test_paging_does_not_repeat_a_row_when_every_sort_key_ties(catalog):
    """Without the record-key tie-break, page 1 and page 2 may show one row
    twice and never show another."""
    # Arrange
    query = Query().ordered_by("source")

    # Act
    pages = [
        {row.values["id"] for row in catalog.search(query.limited(1, offset=n))}
        for n in (0, 1, 2)
    ]

    # Assert
    assert len(set().union(*pages)) == 3


# -- counting -------------------------------------------------------------
def test_count_reports_the_whole_matching_set(catalog):
    # Arrange
    query = Query().where(eq("source", "openneuro"))

    # Act
    total = catalog.count(query)

    # Assert
    assert total == 2


def test_count_ignores_the_query_limit(catalog):
    """Otherwise a paged search reports its page size as the total."""
    # Arrange
    query = Query().limited(1)

    # Act
    total = catalog.count(query)

    # Assert
    assert total == 3


def test_count_excludes_hidden_rows(catalog):
    # Arrange
    query = Query()

    # Act
    total = catalog.count(query)

    # Assert
    assert total == 3


def test_count_with_no_query_counts_the_visible_rows(catalog):
    # Arrange
    store = catalog

    # Act
    total = store.count()

    # Assert
    assert total == 3


def test_tally_groups_by_a_field(catalog):
    # Arrange
    query = Query()

    # Act
    buckets = catalog.tally("source", query)

    # Assert
    assert buckets == {"openneuro": 2, "dandi": 1}


def test_tally_respects_the_query_filter(catalog):
    # Arrange
    query = Query().where(gte("n_subjects", 30))

    # Act
    buckets = catalog.tally("source", query)

    # Assert
    assert buckets == {"openneuro": 1, "dandi": 1}


# -- refusals that need the schema ----------------------------------------
def test_a_query_naming_an_undeclared_field_raises(catalog):
    """The failure a silently empty result set would otherwise hide."""
    # Arrange
    query = Query().where(eq("sauce", "openneuro"))
    # Act
    # Assert
    with pytest.raises(SchemaError, match="does not declare"):
        catalog.search(query)


def test_ordering_by_an_undeclared_field_raises(catalog):
    # Arrange
    query = Query().ordered_by("populariy")
    # Act
    # Assert
    with pytest.raises(SchemaError, match="does not declare"):
        catalog.search(query)


def test_tallying_an_undeclared_field_raises(catalog):
    # Arrange
    group = "sauce"
    # Act
    # Assert
    with pytest.raises(SchemaError, match="does not declare"):
        catalog.tally(group)


def test_contains_on_a_scalar_field_raises(catalog):
    """On a scalar it could only become a substring match, which is a
    different question wearing the same name."""
    # Arrange
    query = Query().where(contains("name", "Motor"))
    # Act
    # Assert
    with pytest.raises(SchemaError, match="needs a JSON field"):
        catalog.search(query)


def test_a_range_on_a_json_field_raises(catalog):
    # Arrange
    query = Query().where(gte("modalities", 3))
    # Act
    # Assert
    with pytest.raises(SchemaError, match="orderable kind"):
        catalog.search(query)

# EOF
