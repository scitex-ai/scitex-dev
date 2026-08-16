#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""An unmatched read is an unanswered question, not an empty answer.

Every case below is a real failure from 2026-08-15, contributed by three
agents working the same night. The two classes are deliberately kept apart:
zero-match (the instrument said nothing) and wrong-instance (the instrument
said something true about the wrong thing).
"""

from __future__ import annotations

import pytest

from scitex_dev.measure import NoMatch, require_group, require_match

#: A real pytest tail. The summary is the LAST line, and reaching for it with
#: `tail -2 | head -1` returns the Docs footer instead -- measured.
_PYTEST_TAIL = (
    "  /path/to/thing.py:246: UserWarning: something\n"
    "-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html\n"
    "524 passed, 8 warnings in 25.26s\n"
)

#: Two generations of engine-init lines in one log. `tail -1` answers
#: confidently and wrongly.
_TWO_GENERATIONS = (
    "2026-08-14 engine-init prefix_caching=True\n"
    "2026-08-15 engine-init prefix_caching=False\n"
)


def test_a_present_fact_is_returned():
    # Arrange
    text = _PYTEST_TAIL
    # Act
    got = require_group(text, r"(\d+) passed", what="the pytest summary")
    # Assert
    assert got == "524"


def test_a_missing_fact_raises_rather_than_returning_empty():
    """THE FIRST CLASS. `gh api` printed a 404 BODY to stdout and an emptiness
    test never fired: 76 repositories recorded as having a variable when 8 had
    none."""
    # Arrange
    text = '{"message": "Not Found"}'
    # Act
    # Assert
    with pytest.raises(NoMatch):
        require_match(text, r"(\d+) passed", what="the pytest summary")


def test_the_error_names_what_was_sought():
    """An error that only says "no match" sends the reader to the pattern."""
    # Arrange
    text = "nothing useful here"
    # Act
    try:
        require_match(text, r"(\d+) passed", what="the pytest summary")
        message = ""
    except NoMatch as exc:
        message = str(exc)
    # Assert
    assert "the pytest summary" in message


def test_the_error_shows_what_was_actually_searched():
    """"I searched the wrong thing" is commoner than "my pattern is wrong",
    and only the text can tell you which."""
    # Arrange
    text = "PERMISSION DENIED opening the log"
    # Act
    try:
        require_match(text, r"(\d+) passed", what="the pytest summary")
        message = ""
    except NoMatch as exc:
        message = str(exc)
    # Assert
    assert "PERMISSION DENIED" in message


def test_two_matches_without_a_disambiguator_raise():
    """THE SECOND CLASS, and the part a naive raise-on-empty helper misses.

    Measured: `tail -1` of engine-init lines returned the PREVIOUS
    generation's config. Nothing was empty, nothing errored, the line was
    real -- and belonged to a different moment.
    """
    # Arrange
    text = _TWO_GENERATIONS
    # Act
    # Assert
    with pytest.raises(NoMatch):
        require_match(text, r"prefix_caching=\w+", what="the prefix-cache setting")


def test_the_ambiguity_error_refuses_to_pick_by_position():
    """The message must say WHY it will not just take the last one, or the
    reader adds `tail -1` back."""
    # Arrange
    text = _TWO_GENERATIONS
    # Act
    try:
        require_match(text, r"prefix_caching=\w+", what="the prefix-cache setting")
        message = ""
    except NoMatch as exc:
        message = str(exc)
    # Assert
    assert "POSITION" in message


def test_identity_selects_the_right_instance():
    """scitex-hpc's actual fix was "an init line carrying today's date"."""
    # Arrange
    text = _TWO_GENERATIONS
    # Act
    got = require_match(
        text,
        r".*prefix_caching=\w+",
        what="the prefix-cache setting",
        identity=r"2026-08-15",
    )
    # Assert
    assert "prefix_caching=False" in got.group(0)


def test_an_identity_nothing_satisfies_raises():
    """Found something real, and it was the wrong instance. That is a
    failure, not a fallback to the nearest candidate."""
    # Arrange
    text = _TWO_GENERATIONS
    # Act
    # Assert
    with pytest.raises(NoMatch):
        require_match(
            text,
            r".*prefix_caching=\w+",
            what="the prefix-cache setting",
            identity=r"2026-08-16",
        )


def test_the_wrong_instance_error_says_it_found_something():
    """Distinguishing "found nothing" from "found the wrong one" sends the
    reader to different places: the pattern versus the source."""
    # Arrange
    text = _TWO_GENERATIONS
    # Act
    try:
        require_match(
            text,
            r".*prefix_caching=\w+",
            what="the prefix-cache setting",
            identity=r"2026-08-16",
        )
        message = ""
    except NoMatch as exc:
        message = str(exc)
    # Assert
    assert "wrong instance" in message


def test_a_single_match_with_identity_still_works():
    """POSITIVE CONTROL. A helper that raised whenever `identity` was passed
    would satisfy the two tests above and be useless -- the narrowing path has
    to actually return a value."""
    # Arrange
    text = "2026-08-15 engine-init prefix_caching=False\n"
    # Act
    got = require_match(
        text, r".*prefix_caching=\w+", what="the setting", identity=r"2026-08-15"
    )
    # Assert
    assert "prefix_caching=False" in got.group(0)


def test_the_footer_trap_is_not_matched_by_a_content_pattern():
    """The original bug: `tail -2 | head -1` returns the Docs footer. A
    content pattern cannot make that mistake, which is the whole argument for
    matching on meaning rather than position."""
    # Arrange
    text = _PYTEST_TAIL
    # Act
    got = require_group(text, r"(\d+ passed[^\n]*)", what="the pytest summary")
    # Assert
    assert got.startswith("524 passed")


# EOF
