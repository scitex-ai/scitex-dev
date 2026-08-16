"""Tests for the audit-all verdict: which audits get to keep a package red.

The defect these pin (scitex-ai/scitex-dev#590): the downgrade a declared
skip rule exists to perform was decided over the run's CONCATENATED
output, so a WARN-tier finding printed by an audit that EXITED 0 vetoed
it. The package stayed red beside its own summary line reading "0
unmasked error(s) ..., 1 masked by skip-rules (1 declared)" — a gate
whose report and whose status disagreed.

Measured on scitex-agent-container, 2026-08-13: audit-project failed on
one declared PS-226, three warnings came from audit-cli (exit 0).
"""

from __future__ import annotations

from scitex_dev._cli.audit._config._skip_rules import SkipRule
from scitex_dev._cli.ecosystem._cmds._audit_masking import classify_output
from scitex_dev._cli.ecosystem._cmds._audit_verdict import (
    decide_pkg_exit,
    failing_audits_are_fully_masked,
)


_DEFERRED = SkipRule("PS-226", "job-name migration — scitex-agent-container#1034")

#: The declared ERROR that made audit-project exit 1.
_MASKED = "ERRO:   [PS-226 §1] src/_jobs_plugin.py:165: name is not hyphenated"
#: A finding nobody deferred.
_UNDECLARED = "ERRO:   [PS-999 §9] src/c.py: something nobody deferred"
#: The vetoing shape: a WARN printed by an audit that EXITED 0, so it
#: provably failed nothing, yet it is attributable and therefore unmasked.
_PASSING_WARN = "WARN:   [§4b] accounts refresh: command has no CliHelp spec"
#: Finding-SHAPED but carrying no rule id — cannot be attributed, so it
#: cannot be shown to be covered by a declared skip.
_UNREADABLE = "ERRO:   [E] src/d.py: severity marker only, no rule id"
#: What a crashed / launch-failed audit leaves behind: no finding at all.
_NO_FINDING = "error: audit-project on scitex-io failed to launch"


# --------------------------------------------------------------------- #
# failing_audits_are_fully_masked                                        #
# --------------------------------------------------------------------- #


def test_a_failing_audit_reporting_only_declared_findings_is_fully_masked():
    """The sanctioned case: the one audit that failed failed on a deferral."""
    # Arrange
    failing = {"audit-project": _MASKED}
    # Act
    result = failing_audits_are_fully_masked(failing, [_DEFERRED])
    # Assert
    assert result is True


def test_a_second_failing_audit_with_an_undeclared_finding_defeats_it():
    """Every audit that failed must be explained, not just one of them."""
    # Arrange
    failing = {"audit-project": _MASKED, "audit-skills": _UNDECLARED}
    # Act
    result = failing_audits_are_fully_masked(failing, [_DEFERRED])
    # Assert
    assert result is False


def test_an_undeclared_warning_from_the_failing_audit_defeats_it():
    """Severity is NOT the discriminator, and deliberately so.

    `audit-skills` and `audit-python-apis` return `0 if not violations
    else 1` — they fail on WARN-tier findings too. So "all unmasked
    findings are warnings" would license downgrading a run those two
    legitimately failed.

    THE AUDITOR IN THIS TEST CHANGED, AND THE DOCSTRING ABOVE IS WHY.
    That reasoning is exactly right and it is about ANY_FINDING auditors.
    It was applied to `audit-project` only because the predicate could not
    tell auditors apart, so it had to be conservative for all of them.
    Now each declares its policy (`_audit_exit_policy`), so the strict
    question is asked of the auditors it is true for — and this test asks
    it of one of them. `audit-project` gets the opposite answer on the
    SAME output, which is the point, and is pinned in
    `test__audit_exit_policy.py`.
    """
    # Arrange
    failing = {"audit-skills": f"{_MASKED}\n{_PASSING_WARN}"}
    # Act
    result = failing_audits_are_fully_masked(failing, [_DEFERRED])
    # Assert
    assert result is False


def test_a_failing_audit_that_reported_no_finding_is_not_fully_masked():
    """A crash is not a deferral — nothing was declared, so nothing is excused."""
    # Arrange
    failing = {"audit-project": _NO_FINDING}
    # Act
    result = failing_audits_are_fully_masked(failing, [_DEFERRED])
    # Assert
    assert result is False


def test_no_failing_audits_at_all_is_not_a_licence_to_downgrade():
    """Empty input means the caller had nothing to downgrade."""
    # Arrange
    failing: dict[str, str] = {}
    # Act
    result = failing_audits_are_fully_masked(failing, [_DEFERRED])
    # Assert
    assert result is False


# --------------------------------------------------------------------- #
# decide_pkg_exit                                                        #
# --------------------------------------------------------------------- #


def _decide(combined: str, failing: dict[str, str], pkg_exit: int = 1):
    report = classify_output(combined, [_DEFERRED])
    return decide_pkg_exit(
        pkg_exit,
        distribution="scitex-io",
        report=report,
        failing_raw=failing,
        skip_rules=[_DEFERRED],
    )


def test_a_warning_from_a_passing_audit_no_longer_keeps_the_package_red():
    """THE #590 CASE. The warning is in the run, not in the failing audit."""
    # Arrange
    combined = f"{_PASSING_WARN}\n{_MASKED}"
    # Act
    exit_code, _warning = _decide(combined, {"audit-project": _MASKED})
    # Assert
    assert exit_code == 0


def test_the_downgrade_is_silent_because_the_inventory_already_speaks():
    """No warning accompanies a downgrade — masking is reported elsewhere."""
    # Arrange
    combined = f"{_PASSING_WARN}\n{_MASKED}"
    # Act
    _exit_code, warning = _decide(combined, {"audit-project": _MASKED})
    # Assert
    assert warning is None


def test_an_undeclared_finding_in_the_failing_audit_still_fails_the_package():
    """Control: declaring one deferral must not blanket-silence the rest."""
    # Arrange
    combined = f"{_MASKED}\n{_UNDECLARED}"
    # Act
    exit_code, _warning = _decide(combined, {"audit-project": combined})
    # Assert
    assert exit_code == 1


def test_an_unreadable_line_anywhere_withholds_the_downgrade():
    """'Everything that failed was declared' cannot be said about an
    unparseable line — it may have been an undeclared error."""
    # Arrange
    combined = f"{_MASKED}\n{_UNREADABLE}"
    # Act
    exit_code, _warning = _decide(combined, {"audit-project": _MASKED})
    # Assert
    assert exit_code == 1


def test_the_withheld_downgrade_says_why_instead_of_staying_silent():
    """A run that stays red for a reason nobody prints is the same dead
    end as one that goes green silently."""
    # Arrange
    combined = f"{_MASKED}\n{_UNREADABLE}"
    # Act
    _exit_code, warning = _decide(combined, {"audit-project": _MASKED})
    # Assert
    assert "could not be classified" in (warning or "")


def test_an_already_green_package_is_returned_untouched():
    """A green package that MEASURED something is returned untouched.

    The verdict removes a red it can explain and otherwise leaves the exit
    code alone. The single exception is a run that inspected nothing, which
    has no verdict to leave alone — see the NO VERDICT tests below.
    """
    # Arrange
    combined = _PASSING_WARN
    # Act
    verdict = _decide(combined, {}, pkg_exit=0)
    # Assert
    assert verdict == (0, None)


# --------------------------------------------------------------------- #
# NO VERDICT: a run that inspected zero lines                            #
# --------------------------------------------------------------------- #


def test_a_run_that_inspected_nothing_gets_no_verdict_not_a_pass():
    """THE DANGEROUS DIRECTION. Zero lines read, exit 0 — green by default.

    `inspected` is the denominator. With a denominator of zero, "0 unmasked
    error(s)" is not a clean bill of health; it is arithmetic on nothing.
    """
    # Arrange
    combined = ""
    # Act
    exit_code, _warning = _decide(combined, {}, pkg_exit=0)
    # Assert
    assert exit_code != 0


def test_a_run_that_inspected_nothing_stays_red_rather_than_going_green():
    """The other pole, and it must NOT be traded away.

    Measured 2026-08-15 on the CI SIF's baked scitex-dev 0.42.0: EXIT=1 with
    "0 unmasked error(s), 0 masked by skip-rules (1 declared); 0 line(s)
    inspected". The fix for a gate that fails having read nothing is to make
    it SAY so — not to make it pass, which would turn a gate that cannot
    discriminate into one that cannot fail.
    """
    # Arrange
    combined = ""
    # Act
    exit_code, _warning = _decide(combined, {"audit-project": _MASKED})
    # Assert
    assert exit_code == 1


def test_the_no_verdict_case_names_itself_rather_than_reporting_a_finding():
    """A reader must be able to tell "did not run" from "found a problem"."""
    # Arrange
    combined = ""
    # Act
    _exit_code, warning = _decide(combined, {})
    # Assert
    assert "NO VERDICT" in (warning or "")


def test_the_no_verdict_message_says_what_to_check():
    """An alarm nobody can act on is an alarm people learn to skip."""
    # Arrange
    combined = ""
    # Act
    _exit_code, warning = _decide(combined, {})
    # Assert
    assert "--path" in (warning or "")


def test_a_run_that_inspected_something_is_not_flagged_no_verdict():
    """POSITIVE CONTROL. A guard that fired on every run would satisfy every
    test above while telling the reader nothing — and would redden the whole
    fleet. This is the test that fails if the predicate is inverted."""
    # Arrange
    combined = _PASSING_WARN
    # Act
    _exit_code, warning = _decide(combined, {}, pkg_exit=0)
    # Assert
    assert "NO VERDICT" not in (warning or "")


def test_the_sanctioned_downgrade_still_works_when_lines_were_inspected():
    """REGRESSION CONTROL: the #590 downgrade must survive the new guard."""
    # Arrange
    combined = _MASKED
    # Act
    exit_code, _warning = _decide(combined, {"audit-project": _MASKED})
    # Assert
    assert exit_code == 0
