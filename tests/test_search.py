#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the unified search module."""

import pytest

from scitex_dev._discovery import invalidate_cache
from scitex_dev.search import parse_query, score_text, search


@pytest.fixture(autouse=True)
def clear_cache():
    invalidate_cache()
    yield
    invalidate_cache()


class TestParseQuery:
    def test_simple_terms(self):
        pq = parse_query("save figure")
        assert pq.optional == ["save", "figure"]
        assert pq.required == []
        assert pq.excluded == []

    def test_required_terms(self):
        pq = parse_query("+ttest statistics")
        assert pq.required == ["ttest"]  # + prefix is stripped
        assert "statistics" in pq.optional

    def test_excluded_terms(self):
        pq = parse_query("stats -deprecated")
        assert "stats" in pq.optional
        assert "deprecated" in pq.excluded

    def test_exact_phrase(self):
        pq = parse_query('"save figure" options')
        assert "save figure" in pq.phrases
        assert "options" in pq.optional

    def test_empty_query(self):
        pq = parse_query("")
        assert pq.is_empty

    def test_combined_operators(self):
        pq = parse_query('+required optional -excluded "exact phrase"')
        assert "required" in pq.required
        assert "optional" in pq.optional
        assert "excluded" in pq.excluded
        assert "exact phrase" in pq.phrases


class TestScoreText:
    def test_exact_match(self):
        pq = parse_query("save")
        score = score_text(pq, "Save data to file")
        assert score > 0

    def test_no_match(self):
        pq = parse_query("xyznonexistent")
        score = score_text(pq, "Save data to file", fuzzy=False)
        assert score == 0

    def test_excluded_returns_negative(self):
        pq = parse_query("stats -internal")
        score = score_text(pq, "internal stats helper")
        assert score == -1

    def test_required_missing_returns_negative(self):
        pq = parse_query("+ttest statistics")
        # "ttest" fuzzy-matches "test", so use fuzzy=False for strict test
        score = score_text(pq, "anova statistics check", fuzzy=False)
        assert score == -1

    def test_required_present(self):
        pq = parse_query("+ttest statistics")
        score = score_text(pq, "ttest independent samples statistics")
        assert score > 0

    def test_phrase_match_higher_score(self):
        pq_phrase = parse_query('"save figure"')
        pq_words = parse_query("save figure")

        text = "save figure to disk"
        score_phrase = score_text(pq_phrase, text)
        score_words = score_text(pq_words, text)

        # Phrase match should score higher per match
        assert score_phrase >= score_words

    def test_fuzzy_match(self):
        pq = parse_query("statisitcs")  # typo
        score = score_text(pq, "statistics module", fuzzy=True)
        assert score > 0

    def test_fuzzy_disabled(self):
        pq = parse_query("statisitcs")  # typo
        score = score_text(pq, "statistics module", fuzzy=False)
        assert score == 0

    def test_case_insensitive(self):
        pq = parse_query("SAVE")
        score = score_text(pq, "save data")
        assert score > 0


class TestSearch:
    def test_empty_query(self):
        result = search("")
        assert result == []

    def test_unknown_scope(self):
        with pytest.raises(ValueError, match="Unknown scope"):
            search("test", scope="invalid")

    def test_max_results(self):
        # Even if many results, should cap at max_results
        result = search("test", max_results=3)
        assert len(result) <= 3
