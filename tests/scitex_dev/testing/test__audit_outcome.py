#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A COULD-NOT-RUN audit must not read as a violation report.

The gate has three answers and had words for two of them. "Found
violations" (FAIL) and "could not run" (UNKNOWN) are different facts about
the world, and the second was being reported in the first's words:

    AssertionError: audit-all reported violations for 'scitex-dev' (exit=1).

Measured 2026-08-11 on scitex-dev PR #567 — a DOC-ONLY diff. A reader who
believes that sentence goes looking for a lint violation. When the true
cause is a missing dependency or an auditor that crashed on import, that
search has no end: the thing being searched for does not exist. Attributing
it took a full CI-log dive.

These tests pin the distinction from both sides, because both directions are
failure modes:

  * a simulated could-not-run must NOT be graded FAIL, and its message must
    not contain the words "reported violations";
  * a genuine violation report must NOT be relabelled UNKNOWN just because
    the surrounding output mentions an import — scitex-dev's own audit
    output says `ModuleNotFoundError` on EVERY run, clean ones included.
"""

from __future__ import annotations

import pytest

from scitex_dev.testing._audit_outcome import (
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNKNOWN,
    classify_audit_outcome,
    could_not_run_evidence,
    finding_lines,
    unknown_message,
    violations_message,
)


#: The line scitex-hub's CI carried from 2026-08-05, verbatim.
HUB_CRASH = "Error: No module named 'requests'"

#: scitex-dev's own audit preamble — present on EVERY invocation, including
#: runs that exit 0. Captured 2026-08-11 from
#: `scitex-dev ecosystem audit-skills scitex-dev --path <worktree>`.
LINTER_NOTICE = (
    "\x1b[33m[scitex-dev linter] WARNING: failed to load plugin 'io': "
    "ModuleNotFoundError: No module named 'scitex_io._linter'"
)

#: A real finding from that same run — warn-tier, and gate-failing.
REAL_FINDING = (
    "WARN:   [SK-704 §FM frontmatter-tags-missing] "
    "/repo/src/scitex_dev/_skills/scitex-dev/25_naming-conventions.md: "
    "missing `tags:` field"
)


class TestACouldNotRunIsNotAViolation:
    """The defect this module exists to prevent, stated as a test."""

    def test_a_missing_dependency_grades_unknown_not_fail(self):
        # Arrange
        output = f"=== audit-cli ===\n{HUB_CRASH}\n"
        # Act
        verdict, _evidence = classify_audit_outcome(1, output)
        # Assert
        assert verdict == VERDICT_UNKNOWN

    def test_the_underlying_error_is_quoted_as_evidence(self):
        # Arrange
        output = f"=== audit-cli ===\n{HUB_CRASH}\n"
        # Act
        _verdict, evidence = classify_audit_outcome(1, output)
        # Assert
        assert evidence == [HUB_CRASH]

    def test_the_message_does_not_claim_violations_were_reported(self):
        # Arrange
        _verdict, evidence = classify_audit_outcome(1, HUB_CRASH)
        # Act
        message = unknown_message("scitex-dev", "scitex-dev ...", 1, evidence, "")
        # Assert
        assert "reported violations" not in message

    def test_the_message_says_could_not_run(self):
        # Arrange
        _verdict, evidence = classify_audit_outcome(1, HUB_CRASH)
        # Act
        message = unknown_message("scitex-dev", "scitex-dev ...", 1, evidence, "")
        # Assert
        assert "COULD NOT RUN" in message

    def test_the_message_quotes_the_underlying_error(self):
        # Arrange
        _verdict, evidence = classify_audit_outcome(1, HUB_CRASH)
        # Act
        message = unknown_message("scitex-dev", "scitex-dev ...", 1, evidence, "")
        # Assert
        assert HUB_CRASH in message

    @pytest.mark.parametrize(
        "line",
        [
            "ModuleNotFoundError: No module named 'yaml'",
            "Traceback (most recent call last):",
            "error: audit-cli on scitex-io failed to launch: [Errno 2]",
            "/bin/sh: 1: scitex-dev: command not found",
            "ImportError: cannot import name 'foo' from 'bar'",
        ],
    )
    def test_every_could_not_run_shape_grades_unknown(self, line):
        # Arrange
        output = line
        # Act
        verdict, _evidence = classify_audit_outcome(1, output)
        # Assert
        assert verdict == VERDICT_UNKNOWN


class TestExitTwoIsAlsoUnknown:
    """Exit 2 is `audit-all` DECLINING to grade, never a finding.

    It is emitted for a usage refusal (`--path requires exactly ONE
    distribution`) and for an unreadable `audit.skip-rules` config, and
    `audit_skills` returns it for "could not locate the tree". None of those
    is a statement about the code under audit.
    """

    def test_a_usage_refusal_grades_unknown(self):
        # Arrange
        output = "error: --path requires exactly ONE distribution (got 2: a, b)."
        # Act
        verdict, _evidence = classify_audit_outcome(2, output)
        # Assert
        assert verdict == VERDICT_UNKNOWN

    def test_the_message_still_says_could_not_run_with_no_evidence(self):
        # Arrange
        _verdict, evidence = classify_audit_outcome(2, "error: bad usage")
        # Act
        message = unknown_message("scitex-dev", "scitex-dev ...", 2, evidence, "")
        # Assert
        assert "COULD NOT RUN" in message


class TestAGenuineViolationStaysAViolation:
    """The other direction. Over-eager UNKNOWN is the same bug reversed.

    If every run that merely MENTIONS an import were graded UNKNOWN, real
    findings would stop being reported as findings — and scitex-dev's own
    audit mentions one on every single invocation.
    """

    def test_a_findings_only_run_grades_fail(self):
        # Arrange
        output = f"WARN: scitex-dev: skills: 1 violation(s)\n{REAL_FINDING}\n"
        # Act
        verdict, _evidence = classify_audit_outcome(1, output)
        # Assert
        assert verdict == VERDICT_FAIL

    def test_the_ever_present_linter_notice_does_not_force_unknown(self):
        # Arrange
        output = f"{LINTER_NOTICE}\nWARN: skills: 1 violation(s)\n{REAL_FINDING}\n"
        # Act
        verdict, _evidence = classify_audit_outcome(1, output)
        # Assert
        assert verdict == VERDICT_FAIL

    def test_the_linter_notice_is_not_could_not_run_evidence(self):
        # Arrange
        output = LINTER_NOTICE
        # Act
        evidence = could_not_run_evidence(output)
        # Assert
        assert evidence == []

    def test_a_finding_line_naming_requests_is_not_a_crash(self):
        """An auditor may report ABOUT an import without failing on one."""
        # Arrange
        output = (
            "ERRO:   [STX-NET001 §2] /repo/a.py:3: requests.get(...) has no "
            "timeout= (module 'requests' import)"
        )
        # Act
        evidence = could_not_run_evidence(output)
        # Assert
        assert evidence == []

    def test_the_failure_message_digests_the_findings(self):
        # Arrange
        output = f"{LINTER_NOTICE}\n{REAL_FINDING}\n"
        _verdict, findings = classify_audit_outcome(1, output)
        # Act
        message = violations_message("scitex-dev", "scitex-dev ...", 1, findings, "")
        # Assert
        assert "SK-704" in message

    def test_the_failure_message_explains_a_warn_tier_exit(self):
        """The `0 unmasked error(s)` + `exit=1` pairing that cost the log dive."""
        # Arrange
        _verdict, findings = classify_audit_outcome(1, REAL_FINDING)
        # Act
        message = violations_message("scitex-dev", "scitex-dev ...", 1, findings, "")
        # Assert
        assert "0 unmasked error(s)" in message


class TestPass:
    def test_exit_zero_is_pass(self):
        # Arrange
        output = "SUCC: scitex-dev: no skills violations"
        # Act
        verdict, _evidence = classify_audit_outcome(0, output)
        # Assert
        assert verdict == VERDICT_PASS

    def test_exit_zero_carries_no_evidence(self):
        # Arrange
        output = HUB_CRASH  # even this: a clean exit is a clean exit
        # Act
        _verdict, evidence = classify_audit_outcome(0, output)
        # Assert
        assert evidence == []


class TestFindingLines:
    """The digest reads rule-bearing lines and nothing else."""

    def test_a_rule_bearing_line_is_a_finding(self):
        # Arrange
        output = REAL_FINDING
        # Act
        found = finding_lines(output)
        # Assert
        assert len(found) == 1

    def test_a_banner_is_not_a_finding(self):
        # Arrange
        output = "INFO: scitex-dev: auditing /repo (branch HEAD, via explicit)"
        # Act
        found = finding_lines(output)
        # Assert
        assert found == []

    def test_colour_codes_do_not_hide_a_finding(self):
        # Arrange
        output = f"\x1b[33m{REAL_FINDING}\x1b[0m"
        # Act
        found = finding_lines(output)
        # Assert
        assert len(found) == 1


# EOF
