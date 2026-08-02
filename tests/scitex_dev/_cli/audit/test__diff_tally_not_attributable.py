#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A roll-up tally must never be attributed to a diff.

Regression for a DOCS-ONLY PR reported as introducing a net-new finding
(scitex-cards, 2026-08-02): 131 findings at HEAD, 131 at baseline, "1
net-new" — the differing pair being the same per-auditor tally with
`4 info` -> `6 info`.

The tally line carries a parenthesised path in its subject, so the
structured finding regex cannot key it; it fell through the ERRO
fail-open and was keyed on its whole text, counts included.

Both directions are asserted. A fix that simply stopped attributing
things would pass the first test and silently disarm the gate, so the
second test is the control that the gate still blames real regressions.
"""

from scitex_dev._cli.audit._diff import (
    TALLY_RULE,
    compute_net_new,
    extract_violation_keys,
)

_BASE = (
    "ERRO: scitex-todo (/repo): project-structure: "
    "14 error(s), 56 warning(s), 4 info"
)
_HEAD = (
    "ERRO: scitex-todo (/repo): project-structure: "
    "14 error(s), 56 warning(s), 6 info"
)


def test_moving_tally_counts_are_not_net_new():
    # Arrange
    head_stdout = _HEAD
    base_stdout = _BASE

    # Act
    net_new = compute_net_new(head_stdout, base_stdout)

    # Assert
    assert net_new == set()


def test_tally_yields_exactly_one_key():
    # Arrange
    stdout = _HEAD

    # Act
    tally = {k for k in extract_violation_keys(stdout) if k.rule == TALLY_RULE}

    # Assert
    assert len(tally) == 1


def test_tally_key_is_identical_across_moving_counts():
    # Arrange
    head = {k for k in extract_violation_keys(_HEAD) if k.rule == TALLY_RULE}

    # Act
    base = {k for k in extract_violation_keys(_BASE) if k.rule == TALLY_RULE}

    # Assert
    assert head == base


def test_tally_is_still_keyed_rather_than_dropped():
    # Arrange
    stdout = _HEAD

    # Act
    keys = extract_violation_keys(stdout)

    # Assert
    assert any(k.rule == TALLY_RULE for k in keys)


def test_a_genuine_new_finding_is_still_attributed():
    # POSITIVE CONTROL. Without this, a fix that attributed nothing at all
    # would pass every assertion above while disarming the gate entirely.
    # Arrange
    base_stdout = _BASE
    head_stdout = _HEAD + "\nERRO: [PS-105] scitex-todo: src/x.py: missing __main__"

    # Act
    net_new = compute_net_new(head_stdout, base_stdout)

    # Assert
    assert len(net_new) == 1


def test_a_finding_merely_mentioning_a_count_is_not_treated_as_a_tally():
    # The tally pattern is tail-anchored so ordinary prose survives.
    # Arrange
    stdout = "ERRO: [PS-999] scitex-todo: t.py: expected 3 error(s) in fixture, got 0"

    # Act
    keys = extract_violation_keys(stdout)

    # Assert
    assert not any(k.rule == TALLY_RULE for k in keys)


# EOF
