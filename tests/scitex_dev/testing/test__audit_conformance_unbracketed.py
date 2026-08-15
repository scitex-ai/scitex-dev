#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""An error without a rule id still counts, and can never be masked.

The classifier only ever looked at lines whose payload began with `[`.
Anything else hit a bare `continue` and landed in NEITHER bucket — so it
could not appear in `non_skipped`, and the guard

    if skipped and not non_skipped:

then masked the entire failure. A gate passing on the strength of an error
it did not know how to read.

The lines that take this path are the ones that matter most: the auditor
reporting that it could not RUN. Measured in the wild — scitex-hub's CI has
carried

    Error: No module named 'requests'

since 2026-08-05, plainly visible in the log and invisible to this
classifier for four days, while both packages' gates reported success.

WHY IT CANNOT BE MASKED, and why that is correct: masking is keyed on rule
id, and these lines carry none, so no skip_rules entry can ever match one.
An auditor that could not run must not be maskable — otherwise the one
signal saying "this measurement did not happen" is the easiest of all to
silence.

The level check is a WHITELIST on purpose. Testing "not a known warn word"
would promote any unrecognised `word:` prefix to an error, so `note:` or
`usage:` would redden a build for no reason — and unexplainable failures are
how a gate gets turned off entirely.
"""

from __future__ import annotations

import pytest

from scitex_dev.testing._audit_conformance import _is_error_tier


class TestTheAuditorCouldNotRun:
    """The real-world line, from hub's CI."""

    def test_a_bare_error_prefix_is_error_tier(self):
        # Arrange
        level = "Error"
        # Act
        counts = _is_error_tier(level)
        # Assert
        assert counts

    def test_an_uppercase_error_is_error_tier(self):
        # Arrange
        level = "ERROR"
        # Act
        counts = _is_error_tier(level)
        # Assert
        assert counts

    @pytest.mark.parametrize(
        "level", ["ERRO", "FAIL", "FAILED", "FATAL", "CRIT", "CRITICAL"]
    )
    def test_the_other_error_words_count(self, level):
        # Arrange
        word = level
        # Act
        counts = _is_error_tier(word)
        # Assert
        assert counts


class TestNonErrorsDoNotRedTheBuild:
    """The whitelist exists so an unknown prefix cannot fail a build."""

    @pytest.mark.parametrize("level", ["WARN", "INFO", "SUCC", "NOTE"])
    def test_warn_tier_words_are_not_error_tier(self, level):
        # Arrange
        word = level
        # Act
        counts = _is_error_tier(word)
        # Assert
        assert not counts

    @pytest.mark.parametrize("level", ["usage", "note", "hint", "summary", "shell"])
    def test_an_unrecognised_prefix_is_not_promoted_to_an_error(self, level):
        # Arrange
        word = level
        # Act
        counts = _is_error_tier(word)
        # Assert
        assert not counts

    def test_an_empty_level_is_not_an_error(self):
        """A line with no `word:` prefix at all must not fail the gate."""
        # Arrange
        level = ""
        # Act
        counts = _is_error_tier(level)
        # Assert
        assert not counts


class TestTheLevelWordIsNormalised:
    def test_surrounding_whitespace_does_not_matter(self):
        # Arrange
        level = "  error  "
        # Act
        counts = _is_error_tier(level)
        # Assert
        assert counts

    def test_mixed_case_does_not_matter(self):
        # Arrange
        level = "FaTaL"
        # Act
        counts = _is_error_tier(level)
        # Assert
        assert counts


# EOF
