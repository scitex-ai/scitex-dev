#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The sub-auditors do not share an exit policy, and the caller was guessing.

Measured on scitex-agent-container's PR #1010: ZERO errors, ZERO masked, 4
warning/info findings, 21 lines inspected — and the build FAILED. Nothing to
mask and nothing to downgrade, so no masking predicate was even reached. A
WARN-only run failed, because `audit-skills` and `audit-python-apis` do not
grade severity.

That one case reconciles readings that looked contradictory: `audit-all
scitex-dev` exits 0 at 190 warnings / 0 errors, exits 0 at 5 warnings / 0
errors, and #1010 exits 1 at 4 warnings / 0 errors. All true. The variable was
never the TIER — it was the EMITTER.
"""

from __future__ import annotations

import pytest

from scitex_dev._cli.audit._config._skip_rules import SkipRule
from scitex_dev._cli.ecosystem._cmds._audit_masking import classify_output
from scitex_dev._cli.ecosystem._cmds._audit_exit_policy import (
    AUDITOR_EXIT_POLICY,
    ExitPolicy,
    failing_audit_is_explained,
    is_downgradeable,
    policy_for,
)

_DEFERRED = SkipRule("PS-226", "job-name migration — sac#1034")
#: The declared ERROR an auditor exited on.
_MASKED_ERROR = "ERRO:   [PS-226 §1] src/_jobs_plugin.py:165: name not hyphenated"
#: A WARNING nobody deferred.
_UNDECLARED_WARN = "WARN:   [§4b] accounts refresh: command has no CliHelp spec"


def _report(text: str):
    return classify_output(text, [_DEFERRED])


@pytest.mark.parametrize(
    "auditor", ["audit-project", "audit-django"]
)
def test_severity_grading_auditors_are_errors_only(auditor: str) -> None:
    """Read from source: `exit_code = 1 if n_errors > 0 else 0`."""
    # Arrange
    name = auditor
    # Act
    policy = policy_for(name)
    # Assert
    assert policy is ExitPolicy.ERRORS_ONLY


@pytest.mark.parametrize(
    "auditor", ["audit-skills", "audit-python-apis"]
)
def test_non_grading_auditors_fail_on_any_finding(auditor: str) -> None:
    """THE #1010 CASE. Read from source: `return 0 if not violations else 1`.

    These two do not look at severity at all, so a lone WARN fails the build.
    """
    # Arrange
    name = auditor
    # Act
    policy = policy_for(name)
    # Assert
    assert policy is ExitPolicy.ANY_FINDING


def test_audit_cli_is_warn_only() -> None:
    """A THIRD policy, and it was not in my design until I read the source.

    `_summary/__init__.py:302`: "return exit code (always 0 -- warn-only)".
    It is a reporting tool, not a gate. That also explains a measurement that
    confused me for hours: `audit-all scitex-dev` exits 0 at 190 warnings
    because those come from the auditor that never fails, while #1010's four
    came from ones that always do.
    """
    # Arrange
    name = "audit-cli"
    # Act
    policy = policy_for(name)
    # Assert
    assert policy is ExitPolicy.WARN_ONLY


def test_a_warn_only_auditor_in_the_failing_set_is_a_contradiction() -> None:
    """It declares it never exits non-zero, yet it is being asked why it did.

    Refusing keeps the contradiction VISIBLE rather than resolving it in
    whichever direction happens to be convenient.
    """
    # Arrange
    report = _report(_MASKED_ERROR)
    # Act
    explained = failing_audit_is_explained("audit-cli", report)
    # Assert
    assert explained is False


def test_an_unmeasured_auditor_has_no_policy() -> None:
    """THE THIRD VALUE. `audit-mcp-tools`'s exit expression was not located,
    so it is absent from the table — and absence must read as "not measured",
    never as "assume the common case"."""
    # Arrange
    name = "audit-mcp-tools"
    # Act
    policy = policy_for(name)
    # Assert
    assert policy is None


def test_an_unmeasured_auditor_is_not_downgradeable() -> None:
    """A downgrade granted on an unasked question is the same defect as one
    refused for no reason, wearing the opposite sign."""
    # Arrange
    name = "audit-mcp-tools"
    # Act
    downgradeable = is_downgradeable(name)
    # Assert
    assert downgradeable is False


def test_a_measured_auditor_is_downgradeable() -> None:
    """POSITIVE CONTROL. A predicate that refused everything would satisfy the
    test above while making the whole mechanism inert — which is the
    gate-that-cannot-pass, the mirror of the gate that cannot fail."""
    # Arrange
    name = "audit-project"
    # Act
    downgradeable = is_downgradeable(name)
    # Assert
    assert downgradeable is True


def test_an_unknown_name_is_not_downgradeable() -> None:
    """A typo'd or renamed auditor must not silently inherit a policy."""
    # Arrange
    name = "audit-does-not-exist"
    # Act
    downgradeable = is_downgradeable(name)
    # Assert
    assert downgradeable is False


def test_an_errors_only_auditor_is_explained_despite_a_stray_warning() -> None:
    """A WARNING cannot have caused an ERRORS_ONLY auditor to exit.

    Asking it the strict "is EVERYTHING masked?" question would hold the
    package red for a finding that is provably not the reason — punishing
    evidence rather than the cause.
    """
    # Arrange
    report = _report(f"{_MASKED_ERROR}\n{_UNDECLARED_WARN}")
    # Act
    explained = failing_audit_is_explained("audit-project", report)
    # Assert
    assert explained is True


def test_an_any_finding_auditor_is_not_explained_by_the_same_output() -> None:
    """THE #1010 BRANCH, and the reason one question does not fit both.

    `audit-skills` does not grade severity, so that same stray warning IS a
    candidate cause of its exit. Identical output, opposite answer.
    """
    # Arrange
    report = _report(f"{_MASKED_ERROR}\n{_UNDECLARED_WARN}")
    # Act
    explained = failing_audit_is_explained("audit-skills", report)
    # Assert
    assert explained is False


def test_an_any_finding_auditor_is_explained_when_everything_is_masked() -> None:
    """POSITIVE CONTROL for the branch above: ANY_FINDING is strict, not
    impossible. A predicate that always refused would pass the test above
    while making declared skips useless for half the auditors."""
    # Arrange
    report = _report(_MASKED_ERROR)
    # Act
    explained = failing_audit_is_explained("audit-skills", report)
    # Assert
    assert explained is True


def test_an_undeclared_auditor_is_never_explained() -> None:
    """Not "assume ERRORS_ONLY", not "assume strict" — we cannot ask the
    right question at all, so no downgrade."""
    # Arrange
    report = _report(_MASKED_ERROR)
    # Act
    explained = failing_audit_is_explained("audit-mcp-tools", report)
    # Assert
    assert explained is False


def test_every_declared_policy_is_a_real_member() -> None:
    """Guards the table itself: a string slipped in place of an enum member
    would type-check nowhere and fail far downstream."""
    # Arrange
    values = list(AUDITOR_EXIT_POLICY.values())
    # Act
    all_members = [isinstance(v, ExitPolicy) for v in values]
    # Assert
    assert all(all_members)


# EOF
