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


# THE SECOND WORDING. Each auditor spells its own tally and the noun is
# not shared: project-structure says `error(s)`, the Python API auditor
# says `violation(s)`. Recognising only the first reproduced the very
# defect this module exists to prevent, on a line nobody had thought to
# check. Measured on scitex-cards 2026-08-13: 141 keys at HEAD against
# 142 at baseline -- FEWER findings -- reported as "1 net-new".
_VIOLATIONS_BASE = "ERRO: scitex-cards: Python API: 410 violation(s)"
_VIOLATIONS_HEAD = "ERRO: scitex-cards: Python API: 409 violation(s)"


def test_a_violations_tally_is_recognised_as_a_tally():
    # Arrange
    stdout = _VIOLATIONS_HEAD

    # Act
    keys = extract_violation_keys(stdout)

    # Assert
    assert any(k.rule == TALLY_RULE for k in keys)


def test_a_shrinking_violations_tally_is_not_net_new():
    # The case that blocked the PR: the count went DOWN and the gate
    # still called it a new finding.
    # Arrange
    head_stdout = _VIOLATIONS_HEAD
    base_stdout = _VIOLATIONS_BASE

    # Act
    net_new = compute_net_new(head_stdout, base_stdout)

    # Assert
    assert net_new == set()


def test_a_violations_tally_keys_identically_across_counts():
    # Arrange
    head = {k for k in extract_violation_keys(_VIOLATIONS_HEAD) if k.rule == TALLY_RULE}

    # Act
    base = {k for k in extract_violation_keys(_VIOLATIONS_BASE) if k.rule == TALLY_RULE}

    # Assert
    assert head == base


def test_prose_ending_in_a_violations_count_is_not_a_tally():
    # CONTROL for the widened noun set: the tail anchor still has to
    # distinguish a tally from a finding that happens to end in a count.
    # Arrange
    stdout = "ERRO: [PS-999] scitex-cards: t.py: fixture declares 2 violation(s)"

    # Act
    keys = extract_violation_keys(stdout)

    # Assert
    assert not any(k.rule == TALLY_RULE for k in keys)


# `_TALLY_COUNT` admits FOUR nouns -- error, warning, violation, finding --
# and until now only two of them were tested. An untested alternative in a
# gate's regex is the §2 shape in miniature: the branch is claimed, nobody
# has ever seen it fire, and a typo in it would present as "this auditor's
# tallies block every PR" long after the edit that caused it.
#
# Found while retiring PR #577, which proposed the same widening against the
# OLD location of this regex (it has since moved to `_diff_keys.py`) and was
# superseded by #607. Its code change was redundant; this coverage was not.
_FINDINGS_BASE = "ERRO: scitex-hpc: CLI conventions: 26 finding(s)"
_FINDINGS_HEAD = "ERRO: scitex-hpc: CLI conventions: 25 finding(s)"


def test_a_findings_tally_is_recognised_as_a_tally():
    # Arrange
    stdout = _FINDINGS_HEAD

    # Act
    keys = extract_violation_keys(stdout)

    # Assert
    assert any(k.rule == TALLY_RULE for k in keys)


def test_a_shrinking_findings_tally_is_not_net_new():
    # The whole point of the noun set: a SHRINKING count must not block.
    # Arrange
    head_stdout = _FINDINGS_HEAD
    base_stdout = _FINDINGS_BASE

    # Act
    net_new = compute_net_new(head_stdout, base_stdout)

    # Assert
    assert net_new == set()


def test_a_warnings_tally_is_recognised_as_a_tally():
    # The fourth noun, and the one most likely to appear alone: sub-auditors
    # that exit non-zero on WARN-tier findings print exactly this shape.
    # Arrange
    stdout = "ERRO: scitex-dev: CLI conventions: 5 warning(s)"

    # Act
    keys = extract_violation_keys(stdout)

    # Assert
    assert any(k.rule == TALLY_RULE for k in keys)


def test_prose_ending_in_a_findings_count_is_not_a_tally():
    # CONTROL for the two nouns added above -- without it, a regex that
    # matched every line ending in a count would satisfy all three.
    # Arrange
    stdout = "ERRO: [PS-999] scitex-hpc: t.py: fixture declares 2 finding(s)"

    # Act
    keys = extract_violation_keys(stdout)

    # Assert
    assert not any(k.rule == TALLY_RULE for k in keys)


# EOF
