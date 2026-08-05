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
banner.

THE FIRST BOUNDARY WAS DRAWN IN THE WRONG PLACE, and this file used to
pin it there. It was "carries a level prefix", which does not survive
contact with scitex-logging: EVERY console line carries a level, so
banners and per-auditor headlines qualified. The note above says so
outright — 431 of those 432 were one banner — and two tests here asserted
that a banner continuation line and an `ERRO: <dist>: N error(s)` headline
were both "unreadable". Re-measured 2026-08-05 on this repo's own captured
audit output: 17 unreadable of 42 inspected, all 17 framing, ZERO true
positives.

That was tolerable only while `unreadable` was printed and nothing else.
It now gates the masking downgrade, and a ~100%-false-positive signal
cannot gate: it would refuse the downgrade on every run and make declared
skip-rules inert fleet-wide.

So the boundary moved to a STRUCTURAL one: a line is unreadable when it is
finding-SHAPED (payload starts with `[`) but carries no rule id, so it
cannot be attributed to a rule and therefore cannot be shown to be masked.
Headlines and banners are framing, counted only in the denominator.

WHAT THAT GIVES UP, recorded so it is not lost: `ERRO: <dist>: N error(s)`
is the auditor's OWN count, and comparing it against the classifier's count
would catch the two-inputs-one-verdict disagreement this module was written
to expose. Nothing ever implemented that comparison — the line was captured
and never reconciled. It wants its own named signal, not a seat in the
bucket that gates. Card: audit-headline-count-vs-classified-count-reconcile.
"""

import pytest

from scitex_dev._cli.ecosystem._cmds._audit_masking import (
    classify_output,
    render_summary,
)

# Verbatim from a real audit-all run: the auditor's own HEADLINE count.
# Framing — it summarises findings, it is not one.
_HEADLINE = "ERRO: scitex-dev: 2 error(s)"
# Verbatim continuation line from the currency-gate advisory banner. Prose.
_BANNER_WARN = "WARN: Judge by CONTENTS, never by directory SIZE."
# A line the classifier CAN read and CAN attribute.
_REAL_FINDING = "ERRO:   [PA-306 §3 no-mocks] scitex-dev: tests/x.py:43: monkeypatch"
# Framing that never claimed to be a finding.
_FRAMING = "=== audit-cli ==="
# Finding-SHAPED but unattributable: the legacy severity marker survived and
# the rule-id bracket did not, so no rule can be named for it.
_UNATTRIBUTABLE = "ERRO:   [E] scitex-dev: tests/x.py:43: rule id missing"


def test_a_finding_shaped_line_with_no_rule_id_is_recorded_as_unreadable():
    # Arrange — it presents as a finding but names no rule, so it cannot be
    # shown to be covered by a declared skip. The genuine UNKNOWN.
    text = _UNATTRIBUTABLE
    # Act
    report = classify_output(text, [])
    # Assert
    assert len(report.unreadable) == 1


def test_an_auditor_headline_is_framing_not_an_unreadable_finding():
    # Arrange — `ERRO: <dist>: N error(s)` summarises findings; it is not
    # one, and the findings it counts are classified on their own lines.
    # This assertion is INVERTED from the original: it used to demand the
    # headline be unreadable, which is why the signal was ~100% false
    # positive and unfit to gate the masking downgrade.
    text = _HEADLINE
    # Act
    report = classify_output(text, [])
    # Assert
    assert report.unreadable == []


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


def test_a_banner_continuation_line_is_framing_not_unreadable():
    # Arrange — wearing a level prefix is not a claim to be a finding:
    # scitex-logging prefixes EVERY console line. This file's own header
    # records a real run of 432 level-prefixed lines, 431 of them this one
    # banner. Counting those as unknowns is what made the bucket useless.
    text = _BANNER_WARN
    # Act
    report = classify_output(text, [])
    # Assert
    assert report.unreadable == []


def test_the_denominator_counts_every_non_blank_line():
    # Arrange
    text = f"{_FRAMING}\n\n{_REAL_FINDING}\n{_HEADLINE}\n"
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
