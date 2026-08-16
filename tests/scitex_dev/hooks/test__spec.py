#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/hooks/test__spec.py
"""HookRule contract tests — construction-time validation and frozen-ness."""

from __future__ import annotations

import dataclasses

import pytest

from scitex_dev.hooks import ALLOWED_EVENTS, ALLOWED_SEVERITIES, HookRule


def _kw(**over):
    base = dict(
        id="dev.some-rule",
        rule="Refuse the thing.",
        reason="Because the thing broke production on a measured date.",
        event="pre-tool-use",
        severity="deny",
        matches=("Bash",),
        provider="scitex-dev",
        script="hooks/x.sh",
    )
    base.update(over)
    return base


# --- shape ------------------------------------------------------------------


def test_allowed_events_includes_pre_tool_use():
    # Arrange
    events = ALLOWED_EVENTS
    # Act
    found = "pre-tool-use" in events
    # Assert
    assert found is True


def test_allowed_severities_are_the_three_enforcement_modes():
    # Arrange
    severities = ALLOWED_SEVERITIES
    # Act
    as_set = set(severities)
    # Assert
    assert as_set == {"deny", "warn", "advise"}


def test_rule_is_frozen():
    # Arrange
    rule = HookRule(**_kw())
    # Act
    act = lambda: rule.__setattr__("id", "other")  # noqa: E731
    # Assert
    with pytest.raises(dataclasses.FrozenInstanceError):
        act()


def test_is_blocking_is_true_for_deny():
    # Arrange
    rule = HookRule(**_kw(severity="deny"))
    # Act
    blocking = rule.is_blocking
    # Assert
    assert blocking is True


def test_is_blocking_is_false_for_warn():
    # Arrange
    rule = HookRule(**_kw(severity="warn"))
    # Act
    blocking = rule.is_blocking
    # Assert
    assert blocking is False


# --- validation fires -------------------------------------------------------


def test_empty_id_is_refused():
    # Arrange
    kwargs = _kw(id="  ")
    # Act
    act = lambda: HookRule(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="non-empty id"):
        act()


def test_unnamespaced_id_is_refused():
    """An id with no dot collides across packages in a federated corpus."""
    # Arrange
    kwargs = _kw(id="some-rule")
    # Act
    act = lambda: HookRule(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="NAMESPACED"):
        act()


def test_id_with_whitespace_is_refused():
    # Arrange
    kwargs = _kw(id="dev.some rule")
    # Act
    act = lambda: HookRule(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="whitespace"):
        act()


def test_empty_rule_is_refused():
    # Arrange
    kwargs = _kw(rule="")
    # Act
    act = lambda: HookRule(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="one sentence"):
        act()


def test_empty_reason_is_refused():
    """The reason is what makes the corpus auditable rather than folkloric."""
    # Arrange
    kwargs = _kw(reason="   ")
    # Act
    act = lambda: HookRule(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="must say WHY"):
        act()


def test_unknown_event_is_refused():
    # Arrange
    kwargs = _kw(event="post-commit")
    # Act
    act = lambda: HookRule(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="event must be one of"):
        act()


def test_unknown_severity_is_refused():
    # Arrange
    kwargs = _kw(severity="block")
    # Act
    act = lambda: HookRule(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="severity must be one of"):
        act()


def test_empty_matches_is_refused():
    # Arrange
    kwargs = _kw(matches=())
    # Act
    act = lambda: HookRule(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="non-empty tuple"):
        act()


def test_untraceable_rule_is_refused():
    """No script, no check, no implemented_in — nobody could locate it."""
    # Arrange
    kwargs = _kw(script=None)
    # Act
    act = lambda: HookRule(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="untraceable"):
        act()


def test_predicate_without_script_is_refused():
    """A predicate resolves relative to its shim, so it needs one."""
    # Arrange
    kwargs = _kw(script=None, check="m:f", predicate="hooks/_p.py")
    # Act
    act = lambda: HookRule(**kwargs)  # noqa: E731
    # Assert
    with pytest.raises(ValueError, match="RELATIVE to"):
        act()


# --- CONTROL ARM ------------------------------------------------------------


def test_implemented_in_alone_is_a_valid_declaration():
    """CONTROL ARM — declare-then-move is the sanctioned migration path.

    A rule whose implementation still lives outside the package must be
    declarable, or the first honest step (make it enumerable) is blocked and
    every leaf is pushed into faking a repo-relative binding instead.
    """
    # Arrange
    kwargs = _kw(script=None, implemented_in="dotfiles:hooks/x.sh")
    # Act
    rule = HookRule(**kwargs)
    # Assert
    assert rule.implemented_in == "dotfiles:hooks/x.sh"


def test_a_well_formed_rule_constructs():
    """CONTROL ARM — the validator must not reject a correct declaration."""
    # Arrange
    kwargs = _kw()
    # Act
    rule = HookRule(**kwargs)
    # Assert
    assert rule.id == "dev.some-rule"
