#!/usr/bin/env python3
# Timestamp: 2026-07-30
# File: tests/scitex_dev/_cli/ecosystem/_cmds/test__audit_masking_denominator.py

"""A summary must report what it looked at, and refuse to hide what it could not read.

`classify_output` used to `continue` past any line `is_violation_line`
rejected. The summary downstream was therefore computed over a silently
narrowed set — it could print "0 unmasked error(s)" while the run exited
non-zero, because the exit code comes from the sub-auditors' return codes
and the count came from whatever survived the filter. Two inputs, one
verdict, and no way for either side to notice the disagreement.

Measured 2026-07-29 on real `audit-all` output: `ERRO: <dist>: N error(s)`
and currency-banner continuation lines both vanished through that
`continue`.

The boundary tested here is as load-bearing as the fix. Treating EVERY
unclassifiable line as unknown would sweep in ordinary framing: one real
run emitted 432 level-prefixed lines of which 431 were a single advisory
banner. Only a line that CLAIMS to be a finding — by carrying a level
prefix — counts as unreadable; prose that never claimed it is framing,
and is counted only in the denominator.
"""

import pytest

from scitex_dev._cli.ecosystem._cmds._audit_masking import (
    classify_output,
    render_summary,
)

# Verbatim from a real audit-all run: unparseable by the key extractor.
_UNREADABLE_ERRO = "ERRO: scitex-dev: 2 error(s)"
# Verbatim continuation line from the currency-gate advisory banner.
_BANNER_WARN = "WARN: Judge by CONTENTS, never by directory SIZE."
# A line the classifier CAN read.
_REAL_FINDING = "ERRO:   [PA-306 §3 no-mocks] scitex-dev: tests/x.py:43: monkeypatch"
# Framing that never claimed to be a finding.
_FRAMING = "=== audit-cli ==="


def test_an_unreadable_error_line_is_recorded_rather_than_skipped():
    # Arrange
    text = _UNREADABLE_ERRO
    # Act
    report = classify_output(text, [])
    # Assert
    assert len(report.unreadable) == 1


def test_a_readable_finding_is_not_counted_as_unreadable():
    # Arrange
    text = _REAL_FINDING
    # Act
    report = classify_output(text, [])
    # Assert
    assert report.unreadable == []


def test_framing_without_a_level_prefix_is_not_unreadable():
    # Arrange — a gate that cannot pass is as broken as one that cannot
    # fail; sweeping in framing would manufacture findings from banners.
    text = _FRAMING
    # Act
    report = classify_output(text, [])
    # Assert
    assert report.unreadable == []


def test_a_banner_continuation_line_is_reported_as_unreadable():
    # Arrange — it wears a level prefix, so it claimed to be a finding.
    text = _BANNER_WARN
    # Act
    report = classify_output(text, [])
    # Assert
    assert len(report.unreadable) == 1


def test_the_denominator_counts_every_non_blank_line():
    # Arrange
    text = f"{_FRAMING}\n\n{_REAL_FINDING}\n{_UNREADABLE_ERRO}\n"
    # Act
    report = classify_output(text, [])
    # Assert — blank lines are not evidence of anything.
    assert report.inspected == 3


def test_the_summary_states_its_denominator():
    # Arrange
    # Act
    line = render_summary(
        "scitex-dev",
        unmasked_errors=0,
        masked=0,
        declared=0,
        inspected=40,
        unreadable=0,
    )
    # Assert
    assert "40 line(s) inspected" in line


def test_the_summary_names_unreadable_lines_when_present():
    # Arrange
    # Act
    line = render_summary(
        "scitex-dev",
        unmasked_errors=0,
        masked=0,
        declared=0,
        inspected=40,
        unreadable=3,
    )
    # Assert
    assert "3 UNREADABLE" in line


def test_the_summary_says_unreadable_lines_are_not_clean():
    # Arrange — "0 errors, 3 unreadable" must not read as a pass.
    # Act
    line = render_summary(
        "scitex-dev",
        unmasked_errors=0,
        masked=0,
        declared=0,
        inspected=40,
        unreadable=3,
    )
    # Assert
    assert "NOT counted as clean" in line


def test_the_summary_omits_the_unreadable_clause_when_there_are_none():
    # Arrange
    # Act
    line = render_summary(
        "scitex-dev",
        unmasked_errors=0,
        masked=0,
        declared=0,
        inspected=40,
        unreadable=0,
    )
    # Assert
    assert "UNREADABLE" not in line


def test_a_summary_cannot_be_rendered_without_its_denominator():
    # Arrange — the enforcement that survives a tired author: omitting the
    # denominator is a TypeError at the call site, not a habit to remember.
    call = lambda: render_summary(  # noqa: E731
        "scitex-dev", unmasked_errors=0, masked=0, declared=0
    )
    # Act
    raised = pytest.raises(TypeError)
    # Assert
    with raised:
        call()
