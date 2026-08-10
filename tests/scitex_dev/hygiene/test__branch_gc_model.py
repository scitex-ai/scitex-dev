#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vocabulary, the age clamp, the protection shield, and the exit-code rank.

Also the SOURCE-LEVEL invariants: some properties of this package are
about what its code does NOT contain, and the only honest way to pin
"there is no remote deletion path" is to read the source.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scitex_dev.hygiene import _branch_gc_model as model
from scitex_dev.hygiene._branch_gc_model import (
    HARD_MIN_AGE_DAYS,
    BranchGcOutcome,
    BranchVerdict,
    RepoBranchGcResult,
    clamp_min_age_days,
    exit_code_for,
    is_protected_name,
)

_HYGIENE_DIR = Path(model.__file__).parent


class _DocstringStripper(ast.NodeTransformer):
    """Drop docstrings so the search reads CODE, not prose about code."""

    def _strip(self, node):
        self.generic_visit(node)
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
        return node

    visit_Module = _strip
    visit_ClassDef = _strip
    visit_FunctionDef = _strip
    visit_AsyncFunctionDef = _strip


def _executable_source() -> str:
    """Every hygiene module's EXECUTABLE source: no comments, no docstrings.

    The claim being tested is "this package cannot perform operation X",
    which is a claim about code. Searching raw text would instead test
    "the package never NAMES X", and these modules deliberately name the
    dangerous operations in order to explain why they are not used.
    ``ast.unparse`` drops comments; the transformer above drops docstrings.
    """
    parts = []
    for path in sorted(_HYGIENE_DIR.glob("*.py")):
        tree = _DocstringStripper().visit(ast.parse(path.read_text(encoding="utf-8")))
        ast.fix_missing_locations(tree)
        parts.append(ast.unparse(tree))
    return "\n".join(parts)


# --------------------------------------------------------------------------
# The age clamp is one-directional.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 1, 7, 13.9])
def test_values_below_the_hard_floor_clamp_up(value):
    """No configuration can lower the floor. This is THE property."""
    # Arrange
    # Act
    result = clamp_min_age_days(value)
    # Assert
    assert result == HARD_MIN_AGE_DAYS


@pytest.mark.parametrize("value", [-5, float("nan"), None])
def test_nonsense_values_fall_back_to_the_default_not_the_floor(value):
    """A nonsense value gets the DEFAULT (30d), which is stricter than the
    floor (14d) — degrade toward conservative, never toward permissive."""
    # Arrange
    # Act
    result = clamp_min_age_days(value)
    # Assert
    assert result == model.DEFAULT_MIN_AGE_DAYS


def test_value_above_the_hard_floor_is_honoured():
    """POSITIVE CONTROL: the clamp is not a constant."""
    # Arrange
    # Act
    result = clamp_min_age_days(90)
    # Assert
    assert result == 90.0


def test_unparseable_value_falls_back_to_the_default():
    # Arrange
    # Act
    result = clamp_min_age_days("thirty")
    # Assert
    assert result == model.DEFAULT_MIN_AGE_DAYS


def test_hard_floor_is_at_least_a_week():
    """A same-day cleanup must be structurally unable to reach live work."""
    # Arrange
    # Act
    # Assert
    assert HARD_MIN_AGE_DAYS >= 7.0


# --------------------------------------------------------------------------
# The protection shield.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["main", "master", "develop", "release/1.0", "release/2026-08"]
)
def test_protected_names_are_protected(name):
    # Arrange
    # Act
    # Assert
    assert is_protected_name(name) is True


def test_ordinary_topic_branch_is_not_protected():
    """POSITIVE CONTROL: the shield does not cover everything."""
    # Arrange
    # Act
    # Assert
    assert is_protected_name("feat/whatever") is False


def test_extra_globs_only_widen_the_shield():
    # Arrange
    # Act
    # Assert
    assert is_protected_name("relocation/x", ("relocation/*",)) is True


# --------------------------------------------------------------------------
# Reporting: UNKNOWN outranks known-bad.
# --------------------------------------------------------------------------


def test_clean_outcome_exits_zero():
    # Arrange
    outcome = BranchGcOutcome(results=(RepoBranchGcResult(repo="/r", cap=10),))
    # Act
    # Assert
    assert exit_code_for(outcome) == 0


def test_over_cap_outcome_exits_one():
    # Arrange
    verdicts = tuple(
        BranchVerdict(name=f"b{i}", keep_reasons=("not-landed",)) for i in range(5)
    )
    outcome = BranchGcOutcome(
        results=(RepoBranchGcResult(repo="/r", cap=1, verdicts=verdicts),)
    )
    # Act
    # Assert
    assert exit_code_for(outcome) == 1


def test_aborted_outcome_exits_one():
    """An abort is a real, actionable problem — never a green pass."""
    # Arrange
    outcome = BranchGcOutcome(
        results=(RepoBranchGcResult(repo="/r", abort_reason="no signal"),)
    )
    # Act
    # Assert
    assert exit_code_for(outcome) == 1


def test_unreadable_repo_outranks_over_cap():
    """UNKNOWN(2) > known-bad(1): an unknown is a known-bad you cannot see."""
    # Arrange
    outcome = BranchGcOutcome(
        results=(
            RepoBranchGcResult(repo="/a", error="not a repo"),
            RepoBranchGcResult(repo="/b", abort_reason="no signal"),
        )
    )
    # Act
    # Assert
    assert exit_code_for(outcome) == 2


def test_keep_reason_breakdown_counts_every_reason():
    """ "31 kept" tells an operator nothing; the breakdown tells them what to do."""
    # Arrange
    result = RepoBranchGcResult(
        repo="/r",
        verdicts=(
            BranchVerdict(name="a", keep_reasons=("not-landed",)),
            BranchVerdict(name="b", keep_reasons=("not-landed", "too-young")),
        ),
    )
    # Act
    # Assert
    assert result.keep_reason_breakdown == {"not-landed": 2, "too-young": 1}


# --------------------------------------------------------------------------
# SOURCE-LEVEL invariants — properties about what the code does NOT contain.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    [
        "--merged",  # the squash-blind predicate; never invoked, not once
        "-D",  # force-delete a branch
        "push",  # NO remote code path exists at all
        "--delete",  # ...nor any remote-delete flag
        "expire",  # the reflog is the second recovery path behind the bundle
        "--prune=",  # `git gc --prune=now` would take it out
        "rm -rf",
        "rmtree",  # no filesystem destruction, by any spelling
        "refs/tags",  # tags: never
        "refs/stash",  # stashes: never
        "refs/notes",
        "--force",
    ],
)
def test_hygiene_code_never_performs_a_forbidden_operation(forbidden):
    """The never-delete list, enforced by reading the code that could break it.

    A behavioural test can only prove the paths it walks. This proves the
    DANGEROUS PATH DOES NOT EXIST — a stronger claim, and the right one
    for a list whose members must stay unreachable by any FUTURE edit too.
    """
    # Arrange
    source = _executable_source()
    # Act
    # Assert
    assert forbidden not in source


def test_positive_control_the_executable_source_is_actually_being_read():
    """The searches above are worthless if the source never loaded.

    An empty search result is not evidence of absence until the same
    search, over the same text, finds something known to be present.
    """
    # Arrange
    source = _executable_source()
    # Act
    # Assert
    assert "update-ref" in source


def test_positive_control_docstring_stripping_removed_the_prose():
    """These modules NAME the forbidden operations to explain them.

    If the stripper silently stopped working, the test above would fail
    loudly rather than pass wrongly — but this pins the mechanism directly
    so the reason for a failure is never ambiguous.
    """
    # Arrange
    source = _executable_source()
    # Act
    # Assert — a phrase that appears ONLY in a docstring.
    assert "A false KEEP" not in source


# EOF
