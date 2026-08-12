#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/hooks/test__discover.py
"""discover_hooks() federation tests.

Every federation test passes ``include_entry_points=False`` so the assertions
are EXACT lists. Without that seam any installed leaf's provider leaks into
the result and the test starts passing or failing for reasons unrelated to
this code.
"""

from __future__ import annotations

from scitex_dev.hooks import ENTRY_POINT_GROUP, HookRule, discover_hooks


def _rule(rid: str, **over) -> HookRule:
    base = dict(
        id=rid,
        rule="Refuse the thing.",
        reason="Because the thing broke production on a measured date.",
        event="pre-tool-use",
        severity="deny",
        matches=("Bash",),
        provider="test-pkg",
        script=f"hooks/{rid.replace('.', '_')}.sh",
    )
    base.update(over)
    return HookRule(**base)


def _ids(rules) -> list[str]:
    return [r.id for r in rules]


# --- group string -----------------------------------------------------------


def test_entry_point_group_is_pinned():
    """A rename here silently unregisters every leaf, so pin the string."""
    # Arrange
    group = ENTRY_POINT_GROUP
    # Act
    value = str(group)
    # Assert
    assert value == "scitex_dev.hooks"


# --- aggregation ------------------------------------------------------------


def test_merges_an_extra_provider():
    # Arrange
    provider = lambda: [_rule("t.alpha")]  # noqa: E731
    # Act
    rules = discover_hooks(include_entry_points=False, extra_providers=[provider])
    # Assert
    assert _ids(rules) == ["t.alpha"]


def test_result_is_sorted_by_id():
    """Determinism: the SET is stable regardless of provider order."""
    # Arrange
    provider = lambda: [_rule("t.zzz"), _rule("t.aaa")]  # noqa: E731
    # Act
    rules = discover_hooks(include_entry_points=False, extra_providers=[provider])
    # Assert
    assert _ids(rules) == ["t.aaa", "t.zzz"]


def test_duplicate_id_keeps_the_first_provider():
    # Arrange
    first = lambda: [_rule("t.dup", rule="ORIGINAL")]  # noqa: E731
    second = lambda: [_rule("t.dup", rule="OVERRIDDEN")]  # noqa: E731
    # Act
    rules = discover_hooks(
        include_entry_points=False, extra_providers=[first, second]
    )
    # Assert
    assert rules[0].rule == "ORIGINAL"


def test_two_rules_binding_one_script_keep_the_first():
    """A shared script cannot be skipped or retired independently."""
    # Arrange
    first = lambda: [_rule("t.aaa", script="hooks/shared.sh")]  # noqa: E731
    second = lambda: [_rule("t.bbb", script="hooks/shared.sh")]  # noqa: E731
    # Act
    rules = discover_hooks(
        include_entry_points=False, extra_providers=[first, second]
    )
    # Assert
    assert _ids(rules) == ["t.aaa"]


def test_a_raising_provider_does_not_take_the_corpus_down():
    """A broken leaf must not disarm every OTHER package's guardrails."""

    def _boom():
        raise RuntimeError("this leaf is broken")

    # Arrange
    good = lambda: [_rule("t.good")]  # noqa: E731
    # Act
    rules = discover_hooks(
        include_entry_points=False, extra_providers=[_boom, good]
    )
    # Assert
    assert _ids(rules) == ["t.good"]


def test_non_hookrule_objects_are_skipped():
    # Arrange
    provider = lambda: [_rule("t.real"), {"id": "not-a-rule"}]  # noqa: E731
    # Act
    rules = discover_hooks(include_entry_points=False, extra_providers=[provider])
    # Assert
    assert _ids(rules) == ["t.real"]


def test_event_filter_selects_one_lifecycle_point():
    # Arrange
    provider = lambda: [  # noqa: E731
        _rule("t.pre", event="pre-tool-use"),
        _rule("t.post", event="post-tool-use"),
    ]
    # Act
    rules = discover_hooks(
        event="post-tool-use",
        include_entry_points=False,
        extra_providers=[provider],
    )
    # Assert
    assert _ids(rules) == ["t.post"]


def test_filtered_out_duplicate_does_not_consume_the_id_slot():
    """The event filter runs BEFORE dedup, so a filtered twin is not a clash."""
    # Arrange
    provider = lambda: [  # noqa: E731
        _rule("t.same", event="post-tool-use", rule="WANTED"),
        _rule("t.same", event="pre-tool-use", rule="FILTERED"),
    ]
    # Act
    rules = discover_hooks(
        event="post-tool-use",
        include_entry_points=False,
        extra_providers=[provider],
    )
    # Assert
    assert rules[0].rule == "WANTED"


# --- CONTROL ARM ------------------------------------------------------------


def test_no_providers_yields_an_empty_corpus():
    """CONTROL ARM — discovery must not invent rules from nowhere.

    A mutation that hardcoded a built-in list back into the aggregator would
    be caught HERE and nowhere else; every positive test above would still
    pass under it.
    """
    # Arrange
    providers = []
    # Act
    rules = discover_hooks(include_entry_points=False, extra_providers=providers)
    # Assert
    assert rules == []
