#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the unified search module."""

import pytest

from scitex_dev._core.discovery import invalidate_cache
from scitex_dev._docs.search import parse_query, score_text, search


@pytest.fixture(autouse=True)
def clear_cache():
    invalidate_cache()
    yield
    invalidate_cache()


class TestParseQuery:
    def test_simple_terms_become_optional_tokens_pq_optional_save_figure(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("save figure")
        assert pq.optional == ["save", "figure"]


    def test_simple_terms_become_optional_tokens_pq_required(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("save figure")
        assert pq.required == []


    def test_simple_terms_become_optional_tokens_pq_excluded(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("save figure")
        assert pq.excluded == []

    def test_required_terms_prefixed_with_plus_are_extracted_pq_required_ttest(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("+ttest statistics")
        assert pq.required == ["ttest"]  # + prefix is stripped


    def test_required_terms_prefixed_with_plus_are_extracted_statistics_in_pq_optional(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("+ttest statistics")
        assert "statistics" in pq.optional

    def test_excluded_terms_prefixed_with_minus_are_extracted_stats_in_pq_optional(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("stats -deprecated")
        assert "stats" in pq.optional


    def test_excluded_terms_prefixed_with_minus_are_extracted_deprecated_in_pq_excluded(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("stats -deprecated")
        assert "deprecated" in pq.excluded

    def test_exact_phrase_in_quotes_is_captured_save_figure_in_pq_phrases(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query('"save figure" options')
        assert "save figure" in pq.phrases


    def test_exact_phrase_in_quotes_is_captured_options_in_pq_optional(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query('"save figure" options')
        assert "options" in pq.optional

    def test_empty_query_flags_is_empty(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("")
        assert pq.is_empty

    def test_combined_operators_all_parse_correctly_required_in_pq_required(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query('+required optional -excluded "exact phrase"')
        assert "required" in pq.required


    def test_combined_operators_all_parse_correctly_optional_in_pq_optional(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query('+required optional -excluded "exact phrase"')
        assert "optional" in pq.optional


    def test_combined_operators_all_parse_correctly_excluded_in_pq_excluded(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query('+required optional -excluded "exact phrase"')
        assert "excluded" in pq.excluded


    def test_combined_operators_all_parse_correctly_exact_phrase_in_pq_phrases(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query('+required optional -excluded "exact phrase"')
        assert "exact phrase" in pq.phrases


class TestScoreText:
    def test_exact_match_yields_positive_score(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("save")
        score = score_text(pq, "Save data to file")
        assert score > 0

    def test_no_match_with_fuzzy_off_yields_zero(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("xyznonexistent")
        score = score_text(pq, "Save data to file", fuzzy=False)
        assert score == 0

    def test_excluded_term_present_returns_negative_score(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("stats -internal")
        score = score_text(pq, "internal stats helper")
        assert score == -1

    def test_required_term_missing_returns_negative_score(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("+ttest statistics")
        # "ttest" fuzzy-matches "test", so use fuzzy=False for strict test
        score = score_text(pq, "anova statistics check", fuzzy=False)
        assert score == -1

    def test_required_term_present_yields_positive_score(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("+ttest statistics")
        score = score_text(pq, "ttest independent samples statistics")
        assert score > 0

    def test_phrase_match_scores_at_least_as_high_as_word_match(self):
        # Arrange
        # Act
        # Assert
        pq_phrase = parse_query('"save figure"')
        pq_words = parse_query("save figure")

        text = "save figure to disk"
        score_phrase = score_text(pq_phrase, text)
        score_words = score_text(pq_words, text)

        # Phrase match should score higher per match
        assert score_phrase >= score_words

    def test_fuzzy_match_handles_typo_in_query(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("statisitcs")  # typo
        score = score_text(pq, "statistics module", fuzzy=True)
        assert score > 0

    def test_fuzzy_disabled_misses_typo_query(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("statisitcs")  # typo
        score = score_text(pq, "statistics module", fuzzy=False)
        assert score == 0

    def test_case_insensitive_matches_uppercase_query(self):
        # Arrange
        # Act
        # Assert
        pq = parse_query("SAVE")
        score = score_text(pq, "save data")
        assert score > 0


class TestSearch:
    def test_empty_query_returns_empty_results(self):
        # Arrange
        # Act
        # Assert
        result = search("")
        assert result == []

    def test_unknown_scope_raises_value_error(self):
        # Arrange
        # Act
        # Assert
        with pytest.raises(ValueError, match="Unknown scope"):
            search("test", scope="invalid")

    def test_max_results_caps_returned_count(self):
        # Even if many results, should cap at max_results
        # Arrange
        # Act
        # Assert
        result = search("test", max_results=3)
        assert len(result) <= 3
