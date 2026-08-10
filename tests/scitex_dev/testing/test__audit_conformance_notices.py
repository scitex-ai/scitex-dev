#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A notice about the measurement is not a violation of the code.

Reported by scitex-hub 2026-08-09, with a replay of the real failing run:

    violation lines classified : 205
    masked by skip_rules       : 151
    NON-SKIPPED                : 1     <- one §10w notice, alone

The guard is ``if skipped and not non_skipped``, so that single unmatched
line discarded a 151-line mask and failed a green tree. The line was the
import-budget auditor saying COULD NOT MEASURE RELIABLY — a deliberate
warn-tier "no verdict" that the classifier counted as a failure.

What makes this worth locking with tests rather than a comment: it is the
SECOND instance. The same defect was reported 2026-07-21 for the ``[defer]``
notice and worked around downstream by adding "defer" to a package's
skip_rules. The workaround held, so the defect survived and came back
wearing a different tag nineteen days later.

A CAUSAL CLAIM THAT WAS WITHDRAWN, recorded so it is not re-derived: the
first report attributed the 112ms baseline to a loaded CI node. scitex-hpc
ran the control and refuted it — the heavily loaded node (load 48/57/62)
measured 18ms while an idle one measured 21ms. Load is not the variable.
The surviving candidate is a COLD-START page-cache miss (39ms first run vs
17-18ms warm) against a fixed bound sampled once, which is a
threshold-design question and NOT what this fix addresses.

This fix is about the CLASSIFIER only, and none of it depends on why the
number was 112. Whatever the auditor reports, a warn-tier "no verdict" is
not a violation of the code under test.

The strings below are the real shapes, not invented ones.
"""

from __future__ import annotations

import pytest

from scitex_dev.testing._audit_conformance import _is_gate_violation


class TestACouldNotMeasureNoticeIsNotAViolation:
    """UNKNOWN must not collapse into the failure pole."""

    def test_the_import_budget_notice_does_not_count(self):
        # Arrange
        payload = (
            "[§10w] scitex-hub: §10 import-budget SKIPPED — COULD NOT MEASURE "
            "RELIABLY: bare-interpreter baseline 112ms exceeds the 100ms bound"
        )
        # Act
        counts = _is_gate_violation("WARN", payload)
        # Assert
        assert not counts

    def test_it_does_not_count_even_without_a_level_word(self):
        """Some emitters print the bracket with no `WARN: ` prefix."""
        # Arrange
        payload = "[§10w] could not measure"
        # Act
        counts = _is_gate_violation("", payload)
        # Assert
        assert not counts

    def test_the_plain_import_budget_rule_also_does_not_count(self):
        """§10 describes the machine, not the diff — same as _diff.py says."""
        # Arrange
        payload = "[§10] import budget"
        # Act
        counts = _is_gate_violation("", payload)
        # Assert
        assert not counts


class TestTheDeferNoticeIsNotAViolation:
    """The 2026-07-21 report, fixed at the source this time."""

    def test_a_defer_notice_does_not_count(self):
        # Arrange
        payload = "[defer] 12 finding(s) suppressed"
        # Act
        counts = _is_gate_violation("", payload)
        # Assert
        assert not counts

    def test_a_tally_line_does_not_count(self):
        """A tally is arithmetic over findings already counted."""
        # Arrange
        payload = "[TALLY] 44 error(s)"
        # Act
        counts = _is_gate_violation("", payload)
        # Assert
        assert not counts


class TestRealFindingsStillCount:
    """The gate must still fail. A fix that silences everything is worse."""

    def test_an_error_tier_finding_counts(self):
        # Arrange
        payload = "[PS-204 §2 orphan-test-file] tests/foo.py: no matching src"
        # Act
        counts = _is_gate_violation("ERRO", payload)
        # Assert
        assert counts

    def test_a_legacy_bracket_e_finding_counts(self):
        # Arrange
        payload = "[E] [PS-202 §2 src-tests-mirror-dir-missing] src/x: no tests"
        # Act
        counts = _is_gate_violation("ERRO", payload)
        # Assert
        assert counts

    def test_a_finding_with_no_level_word_counts(self):
        """Canonical auditors print the rule with no level prefix."""
        # Arrange
        payload = "[PS-224 §1 runner-destination-unregistered] cla.yml::call"
        # Act
        counts = _is_gate_violation("", payload)
        # Assert
        assert counts


class TestSeverityIsRead:
    """It was stripped only to reach the bracket, then thrown away."""

    def test_a_warn_tier_finding_does_not_fail_the_gate(self):
        """PS-169 is advisory since 0.43.0 — it must not red a build."""
        # Arrange
        payload = "[PS-169 §3 hosted-runner] tests.yml::test-summary"
        # Act
        counts = _is_gate_violation("WARN", payload)
        # Assert
        assert not counts

    def test_an_info_line_does_not_fail_the_gate(self):
        # Arrange
        payload = "[PS-100 §1 something] informational"
        # Act
        counts = _is_gate_violation("INFO", payload)
        # Assert
        assert not counts

    @pytest.mark.parametrize("level", ["ERRO", "ERROR", "FAIL"])
    def test_error_tier_levels_still_fail_the_gate(self, level):
        # Arrange
        payload = "[PS-204 §2 orphan-test-file] tests/foo.py"
        # Act
        counts = _is_gate_violation(level, payload)
        # Assert
        assert counts


class TestARuleIdPrefixIsNotEnough:
    """`§10` must not swallow a hypothetical `§100`."""

    def test_a_longer_rule_id_is_not_matched_by_a_shorter_one(self):
        # Arrange
        payload = "[§100 §2 something-real] a genuine finding"
        # Act
        counts = _is_gate_violation("ERRO", payload)
        # Assert
        assert counts


# EOF
