"""Tests for audit-all's skip-rule masking + the masked inventory.

Honouring a declared deferral must never be silent. These tests pin the
two halves of that contract: the classification (what counts as masked)
and the inventory (that the count, the rule ids and the written
rationales are all emitted).
"""

from __future__ import annotations

from scitex_dev._cli.audit._config._skip_rules import SkipRule
from scitex_dev._cli.ecosystem._cmds._audit_masking import (
    classify_output,
    is_error_line,
    is_violation_line,
    line_matches_rule,
    render_inventory,
    render_summary,
)


_DEFERRED = SkipRule("PS-139", "TQ-migration campaign — scitex-hub#412")
_OTHER = SkipRule("PS-202", "CLI noun-verb migration — scitex-hub#415")

_CANONICAL = "ERRO:   [PS-139 §2] src/a.py: uses the legacy TQ helper"
_LEGACY = "  [E] [PS-139 §2] src/b.py: uses the legacy TQ helper"
_UNDECLARED = "ERRO:   [PS-999 §9] src/c.py: something nobody deferred"
#: Finding-SHAPED (payload starts with `[`) but carrying only the legacy
#: severity marker and no rule id, so it cannot be attributed to any rule
#: and therefore cannot be shown to be masked. The genuine UNKNOWN.
_UNREADABLE = "ERRO:   [E] src/d.py: severity marker only, no rule id"

#: Framing the auditors print constantly. Carries a level prefix but is not
#: finding-shaped. Must be counted in `inspected` and NOWHERE else — this is
#: the shape that made `unreadable` ~100% false-positive before.
_FRAMING = "INFO: scitex-hub: auditing /repo (branch develop, HEAD abc1234)"


# --------------------------------------------------------------------- #
# Line recognition                                                       #
# --------------------------------------------------------------------- #


def test_canonical_violation_line_is_recognised():
    """`ERRO:   [PS-139 §2] ...` is the shape every current auditor prints."""
    # Arrange
    line = _CANONICAL
    # Act
    result = is_violation_line(line)
    # Assert
    assert result is True


def test_legacy_violation_line_is_recognised():
    """`  [E] [PS-139 §2] ...` is audit-summary's older shape."""
    # Arrange
    line = _LEGACY
    # Act
    result = is_violation_line(line)
    # Assert
    assert result is True


def test_prose_line_is_not_a_violation_line():
    """Headlines and disclaimers must not be classified as findings."""
    # Arrange
    line = "SUCC: scitex-hub: no skills violations"
    # Act
    result = is_violation_line(line)
    # Assert
    assert result is False


def test_rule_id_matches_inside_bracketed_token():
    """`[PS-139 §2]` reports rule PS-139."""
    # Arrange
    line = _CANONICAL
    # Act
    result = line_matches_rule(line, "PS-139")
    # Assert
    assert result is True


def test_rule_id_does_not_match_a_longer_id_with_the_same_prefix():
    """`PS-139` must not swallow `PS-1390` — deferrals are per-rule."""
    # Arrange
    line = "ERRO:   [PS-1390 §2] src/a.py: a different rule"
    # Act
    result = line_matches_rule(line, "PS-139")
    # Assert
    assert result is False


# --------------------------------------------------------------------- #
# Classification                                                         #
# --------------------------------------------------------------------- #


def test_declared_rule_violation_is_masked():
    """A finding on a declared rule lands in the masked bucket."""
    # Arrange
    text = _CANONICAL
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert report.masked_count == 1


def test_undeclared_rule_violation_is_not_masked():
    """A finding nobody deferred still counts against the run."""
    # Arrange
    text = _UNDECLARED
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert report.unmasked_count == 1


def test_run_with_only_declared_violations_is_fully_masked():
    """Fully-masked runs are the ones whose exit code flips to 0."""
    # Arrange
    text = f"{_CANONICAL}\n{_LEGACY}"
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert report.fully_masked is True


def test_run_with_one_undeclared_violation_is_not_fully_masked():
    """One undeclared finding is enough to keep the run red."""
    # Arrange
    text = f"{_CANONICAL}\n{_UNDECLARED}"
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert report.fully_masked is False


def test_no_findings_at_all_is_not_fully_masked():
    """An empty run must not be reported as 'masked' — nothing was."""
    # Arrange
    text = "SUCC: scitex-hub: no skills violations"
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert report.fully_masked is False


# --------------------------------------------------------------------- #
# is_answerable / the unreadable guard on the downgrade                   #
# --------------------------------------------------------------------- #


def test_report_with_nothing_unreadable_is_answerable():
    """Positive control: a fully-read run licenses a verdict."""
    # Arrange
    text = f"{_CANONICAL}\n{_LEGACY}"
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert report.is_answerable() is True


def test_report_with_an_unreadable_line_is_not_answerable():
    """A line that claimed to be a finding and could not be read is UNKNOWN."""
    # Arrange
    text = _UNREADABLE
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert report.is_answerable() is False


def test_unmasked_finding_does_not_make_a_report_unanswerable():
    """A red verdict is an ANSWER — only unreadability withholds one.

    Guards against the over-broad fix: folding `unmasked` into
    `is_answerable` would make every failing run 'unanswerable' and
    quietly change what the predicate means.
    """
    # Arrange
    text = _UNDECLARED
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert report.is_answerable() is True


def test_unreadable_line_defeats_the_fully_masked_downgrade():
    """The downgrade claims 'everything that failed was declared'.

    That sentence cannot be said about a line nobody could parse, so a
    run whose readable findings are all masked must still NOT be
    reported as fully masked. This is the pair to
    test_run_with_only_declared_violations_is_fully_masked, which uses
    the identical masked lines WITHOUT the unreadable one and expects
    True — so this asserts the unreadable line is what flips it.
    """
    # Arrange
    text = f"{_CANONICAL}\n{_LEGACY}\n{_UNREADABLE}"
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert report.fully_masked is False


def test_framing_lines_are_not_counted_as_unreadable():
    """Banners and headlines are not findings, however they are prefixed.

    scitex-logging prefixes EVERY console line with a level word, so a
    level prefix says nothing about whether a line claimed to be a
    finding. Measured 2026-08-05 on this repo's own captured audit
    output: 17 'unreadable' of 42 inspected, all 17 framing, zero true
    positives.
    """
    # Arrange
    text = "\n".join(
        [
            _FRAMING,
            "SUCC: scitex-hub: no skills violations",
            "WARN: scitex-hub: CLI conventions: 7 warning(s)",
            "ERRO: scitex-hub (/repo): project-structure: 1 error(s), 9 info",
        ]
    )
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert report.unreadable == []


def test_framing_lines_do_not_defeat_the_fully_masked_downgrade():
    """The guard must close the hole without making skip-rules inert.

    Every failing audit prints a headline, so if framing counted as
    unreadable the downgrade would be refused on essentially every run
    and declared deferrals would stop working fleet-wide. That is a
    worse failure than the one the guard fixes, so it is pinned here.
    """
    # Arrange
    text = f"{_FRAMING}\n{_CANONICAL}\n{_LEGACY}"
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert report.fully_masked is True


def test_attributable_finding_matching_no_declared_rule_is_unmasked_not_unreadable():
    """Carrying a rule id nobody declared is an ANSWER (red), not an unknown."""
    # Arrange
    text = _UNDECLARED
    # Act
    report = classify_output(text, [_DEFERRED])
    # Assert
    assert (report.unmasked_count, report.unreadable) == (1, [])


def test_zero_declared_skips_masks_nothing():
    """With no deferrals declared, every finding stays unmasked."""
    # Arrange
    text = _CANONICAL
    # Act
    report = classify_output(text, [])
    # Assert
    assert report.unmasked_count == 1


# --------------------------------------------------------------------- #
# The masked inventory                                                   #
# --------------------------------------------------------------------- #


def test_inventory_reports_the_total_masked_count():
    """The headline count is the number the summary must not omit."""
    # Arrange
    report = classify_output(f"{_CANONICAL}\n{_LEGACY}", [_DEFERRED])
    # Act
    text = "\n".join(render_inventory(report, "scitex-hub"))
    # Assert
    assert "2 violation(s) masked" in text


def test_inventory_names_each_masked_rule_id():
    """Rule ids must be visible, not just an aggregate count."""
    # Arrange
    report = classify_output(_CANONICAL, [_DEFERRED])
    # Act
    text = "\n".join(render_inventory(report, "scitex-hub"))
    # Assert
    assert "[PS-139]" in text


def test_inventory_prints_the_written_rationale():
    """The rationale is the whole reason the deferral is sanctioned."""
    # Arrange
    report = classify_output(_CANONICAL, [_DEFERRED])
    # Act
    text = "\n".join(render_inventory(report, "scitex-hub"))
    # Assert
    assert "TQ-migration campaign — scitex-hub#412" in text


def test_inventory_lists_a_declared_rule_that_masked_nothing():
    """A stale deferral is worth seeing — it is now removable."""
    # Arrange
    report = classify_output(_CANONICAL, [_DEFERRED, _OTHER])
    # Act
    text = "\n".join(render_inventory(report, "scitex-hub"))
    # Assert
    assert "now removable" in text


def test_inventory_is_empty_when_no_skips_are_declared():
    """Repos with no deferrals get no inventory noise."""
    # Arrange
    report = classify_output(_CANONICAL, [])
    # Act
    lines = render_inventory(report, "scitex-hub")
    # Assert
    assert lines == []


# --------------------------------------------------------------------- #
# The summary line                                                       #
# --------------------------------------------------------------------- #


def test_summary_states_the_unmasked_error_count():
    """Real errors are the number that drives the exit code."""
    # Arrange
    args = dict(unmasked_errors=0, masked=150, declared=4, inspected=0, unreadable=0)
    # Act
    line = render_summary("scitex-hub", **args)
    # Assert
    assert "0 unmasked error(s)" in line


def test_summary_states_the_masked_count_alongside_it():
    """Reporting only '0 errors' while 150 are masked is a lie of omission."""
    # Arrange
    args = dict(unmasked_errors=0, masked=150, declared=4, inspected=0, unreadable=0)
    # Act
    line = render_summary("scitex-hub", **args)
    # Assert
    assert "150 masked by skip-rules" in line


def test_summary_states_zero_masked_when_nothing_is_deferred():
    """The masked number is unconditional, never omitted when zero."""
    # Arrange
    args = dict(unmasked_errors=3, masked=0, declared=0, inspected=0, unreadable=0)
    # Act
    line = render_summary("scitex-dev", **args)
    # Assert
    assert "0 masked by skip-rules" in line


# --------------------------------------------------------------------- #
# Severity accuracy — warnings are not errors                            #
# --------------------------------------------------------------------- #


def test_error_prefixed_line_counts_as_an_error():
    """`ERRO:` is scitex-logging's error marker."""
    # Arrange
    line = _CANONICAL
    # Act
    result = is_error_line(line)
    # Assert
    assert result is True


def test_warning_prefixed_line_does_not_count_as_an_error():
    """A warning must not be reported as an error — only errors fail CI."""
    # Arrange
    line = "WARN:   [§12] scitex-dev ecosystem gui: missing verbs"
    # Act
    result = is_error_line(line)
    # Assert
    assert result is False


def test_unmasked_error_count_excludes_warnings():
    """7 warnings + 1 error is 1 error, not 8."""
    # Arrange
    text = "\n".join(
        ["WARN:   [§12] a: w"] * 7 + ["ERRO:   [PS-204 §2] b: e"]
    )
    # Act
    report = classify_output(text, [])
    # Assert
    assert report.unmasked_error_count == 1


def test_summary_reports_warnings_separately_from_errors():
    """The warning count is surfaced, not folded into the error count."""
    # Arrange
    args = dict(unmasked_errors=1, unmasked_total=8, masked=0, declared=0, inspected=0, unreadable=0)
    # Act
    line = render_summary("scitex-dev", **args)
    # Assert
    assert "1 unmasked error(s) (+7 warning/info finding(s))" in line
