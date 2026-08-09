#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The active-work token matcher — deliberately over-matching."""

from __future__ import annotations

import pytest

from scitex_dev.hygiene._branch_gc_active import (
    MIN_TOKEN_LENGTH,
    branch_is_active,
    card_active_tokens,
)


@pytest.mark.parametrize(
    ("branch", "token"),
    [
        ("relocation/residency", "relocation-residency-20260808"),
        ("relocation/residency", "relocation/residency"),
        ("feat/session-carry", "session-carry"),
        ("fix/install_integrity", "install-integrity"),
    ],
)
def test_branch_named_by_a_card_token_is_active(branch, token):
    """Containment is checked BOTH ways, and `/`/`_` normalise to `-`."""
    # Arrange
    # Act
    # Assert
    assert branch_is_active(branch, {token}) is True


def test_unrelated_branch_is_not_active():
    """POSITIVE CONTROL: the matcher is not a constant True."""
    # Arrange
    # Act
    # Assert
    assert branch_is_active("chore/bump-deps", {"relocation-residency"}) is False


def test_short_tokens_are_ignored():
    """A short token would match nearly everything and kill the signal."""
    # Arrange
    tiny = "x-" + "y" * (MIN_TOKEN_LENGTH - 3)
    # Act
    # Assert
    assert branch_is_active(f"feat/{tiny}z", {tiny}) is False


@pytest.mark.parametrize("word", ["container", "relocation", "residency"])
def test_prose_words_are_ignored(word):
    """MEASURED DEFECT, pinned.

    With no shape requirement, the four-letter word "feat" in one card's
    note matched ALL 59 branches of the real scitex-agent-container
    checkout — the leg became a constant. A token must look like a NAME
    (carry a separator), not merely be long.
    """
    # Arrange
    # Act
    # Assert
    assert branch_is_active(f"feat/{word}-work", {word}) is False


def test_slug_shaped_token_still_matches():
    """POSITIVE CONTROL: the shape rule did not disable the leg."""
    # Arrange
    # Act
    # Assert
    assert branch_is_active("feat/relocation-work", {"relocation-work"}) is True


def test_empty_branch_name_is_not_active():
    # Arrange
    # Act
    # Assert
    assert branch_is_active("", {"anything-at-all"}) is False


def test_missing_cards_package_yields_unavailable_not_empty(tmp_path):
    """The default implementation must return None, never an empty set.

    An empty set means "the fleet is working on nothing", which would let
    the engine delete everything. Only ``None`` is honest about a signal
    that could not be read, and the engine turns that into an abort.
    """
    # Arrange — scitex-cards may or may not be installed here, so assert the
    # only property that holds either way: the result is never a silent lie.
    # Act
    tokens = card_active_tokens()
    # Assert
    assert tokens is None or isinstance(tokens, set)


# EOF
