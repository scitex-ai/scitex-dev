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
    legitimately failed. Each audit is asked the strict question instead:
    is EVERYTHING you reported masked?
    """
    # Arrange
    failing = {"audit-project": f"{_MASKED}\n{_PASSING_WARN}"}
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
    """The verdict never reddens; it only ever removes a red it can explain."""
    # Arrange
    combined = _PASSING_WARN
    # Act
    verdict = _decide(combined, {}, pkg_exit=0)
    # Assert
    assert verdict == (0, None)
