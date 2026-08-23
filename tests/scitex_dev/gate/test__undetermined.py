"""The gate's third verdict: ran, and could not tell.

The behaviour under test is the one scitex-cards measured on their own
release-ancestry detector on 2026-08-23 — an unresolvable branch was skipped
and the gate passed, so a failed fetch or a shallow clone certified a release.
These tests pin the two things that prevent it: an undetermined result BLOCKS,
and it is distinguishable from a real failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev.gate._config import GateConfig
from scitex_dev.gate._run import report_to_dict, run_gate
from scitex_dev.gate._spec import Finding, GateCheck, GateResult


def _check(check_id: str, result: GateResult) -> GateCheck:
    """A stage-'submit' check that returns `result` whatever it is given."""
    return GateCheck(
        id=check_id,
        stage="pre-submission",
        run=lambda workdir, config: result,
    )


def _run(tmp_path: Path, check: GateCheck, *, enforce: bool = False):
    """Run one check in isolation.

    `enforce` is explicit and defaults to OFF because the gate is
    warn-by-default and hard-enforce is opt-in per check id (operator
    ruling 2026-07-03). Blocking therefore has two conditions, and a test
    that asserts on blocking without setting this is asserting a property
    the framework deliberately does not have.
    """
    return run_gate(
        tmp_path,
        "pre-submission",
        config=GateConfig(enforce=frozenset({check.id}) if enforce else frozenset()),
        extra_providers=[lambda: [check]],
        include_entry_points=False,
        include_builtins=False,
    )


def test_cannot_determine_requires_a_reason():
    """An unexplained refusal is indistinguishable from a bug in the check."""
    # Arrange
    blank = "   "
    # Act
    raised = pytest.raises(ValueError)
    # Assert
    with raised:
        GateResult.cannot_determine(blank)


def test_cannot_determine_reports_not_passed():
    """`passed` is False so a consumer predating this field still blocks."""
    # Arrange
    reason = "origin/develop did not resolve (shallow clone?)"
    # Act
    result = GateResult.cannot_determine(reason)
    # Assert
    assert result.passed is False


def test_cannot_determine_marks_itself_undetermined():
    """The third verdict is readable as itself, not only as a failure."""
    # Arrange
    reason = "origin/develop did not resolve (shallow clone?)"
    # Act
    result = GateResult.cannot_determine(reason)
    # Assert
    assert result.undetermined is True


def test_an_enforced_undetermined_check_blocks_the_gate(tmp_path):
    """THE CONTROL: this is the outcome that used to pass silently."""
    # Arrange
    check = _check("x", GateResult.cannot_determine("the ref did not resolve"))
    # Act
    report = _run(tmp_path, check, enforce=True)
    # Assert
    assert report.blocking is True


def test_an_enforced_passing_check_still_does_not_block(tmp_path):
    """The contrast case — otherwise the test above proves nothing."""
    # Arrange
    check = _check("x", GateResult(passed=True))
    # Act
    report = _run(tmp_path, check, enforce=True)
    # Assert
    assert report.blocking is False


def test_an_unenforced_undetermined_check_does_not_block(tmp_path):
    """Warn-by-default applies to the third verdict too, on purpose.

    An undetermined result is not a licence to override the repo's
    enforcement choice. What it must NOT do is disappear — see the next
    test, which pins that it stays visible while non-blocking.
    """
    # Arrange
    check = _check("x", GateResult.cannot_determine("the ref did not resolve"))
    # Act
    report = _run(tmp_path, check, enforce=False)
    # Assert
    assert report.blocking is False


def test_an_unenforced_undetermined_check_is_still_flagged(tmp_path):
    """Non-blocking must not mean invisible — that was the whole defect."""
    # Arrange
    check = _check("x", GateResult.cannot_determine("the ref did not resolve"))
    # Act
    report = _run(tmp_path, check, enforce=False)
    # Assert
    assert report.outcomes[0].undetermined is True


def test_an_undetermined_outcome_is_flagged_on_the_outcome(tmp_path):
    """A reader can tell "could not tell" from "failed"."""
    # Arrange
    check = _check("x", GateResult.cannot_determine("the ref did not resolve"))
    # Act
    report = _run(tmp_path, check)
    # Assert
    assert report.outcomes[0].undetermined is True


def test_an_ordinary_failure_is_not_flagged_undetermined(tmp_path):
    """The flag must separate the two, not decorate every failure."""
    # Arrange
    check = _check("x", GateResult(passed=False))
    # Act
    report = _run(tmp_path, check)
    # Assert
    assert report.outcomes[0].undetermined is False


def test_the_reason_reaches_the_outcome(tmp_path):
    """What was unavailable is what the reader needs; it must survive."""
    # Arrange
    check = _check("x", GateResult.cannot_determine("origin/develop absent"))
    # Act
    report = _run(tmp_path, check)
    # Assert
    assert report.outcomes[0].undetermined_reason == "origin/develop absent"


def test_a_distinct_finding_kind_is_attached(tmp_path):
    """`check_undetermined`, not `check_failed` and not `check_crashed`."""
    # Arrange
    check = _check("x", GateResult.cannot_determine("origin/develop absent"))
    # Act
    report = _run(tmp_path, check)
    # Assert
    assert [f.kind for f in report.outcomes[0].findings] == ["check_undetermined"]


def test_the_attached_finding_names_what_was_unavailable(tmp_path):
    """The message must carry the reason, not just the fact of refusal."""
    # Arrange
    check = _check("x", GateResult.cannot_determine("origin/develop absent"))
    # Act
    report = _run(tmp_path, check)
    # Assert
    assert "origin/develop absent" in report.outcomes[0].findings[0].message


def test_the_checks_own_findings_are_preserved(tmp_path):
    """The undetermined finding is appended, not substituted."""
    # Arrange
    own = Finding(check_id="x", kind="context", message="what I did see")
    check = _check("x", GateResult.cannot_determine("no ref", findings=(own,)))
    # Act
    report = _run(tmp_path, check)
    # Assert
    assert [f.kind for f in report.outcomes[0].findings] == [
        "context",
        "check_undetermined",
    ]


def test_a_crash_is_still_reported_as_a_crash(tmp_path):
    """A bug in the check and an unobservable subject stay distinguishable."""

    # Arrange
    def _boom(workdir, config):
        raise RuntimeError("bug in the check itself")

    check = GateCheck(id="x", stage="pre-submission", run=_boom)
    # Act
    report = _run(tmp_path, check)
    # Assert
    assert [f.kind for f in report.outcomes[0].findings] == ["check_crashed"]


def test_a_skipped_check_is_not_undetermined(tmp_path):
    """Deliberately-not-run and ran-but-unknowable are opposites."""
    # Arrange
    check = GateCheck(
        id="x",
        stage="pre-submission",
        run=lambda workdir, config: GateResult(passed=True),
        requires="a_module_that_does_not_exist_anywhere",
    )
    # Act
    report = _run(tmp_path, check)
    # Assert
    assert (report.outcomes[0].ran, report.outcomes[0].undetermined) == (
        False,
        False,
    )


def test_the_json_view_exposes_the_third_verdict(tmp_path):
    """`gate --json` consumers must be able to tell the two apart."""
    # Arrange
    check = _check("x", GateResult.cannot_determine("origin/develop absent"))
    # Act
    payload = report_to_dict(_run(tmp_path, check))
    # Assert
    assert payload["checks"][0]["undetermined"] is True


def test_a_result_without_the_new_fields_still_runs(tmp_path):
    """A leaf built against an older scitex-dev must not take out the runner.

    Its GateResult has no `undetermined` attribute at all; the runner reads it
    defensively, so an old provider degrades to the previous two-valued
    behaviour instead of crashing every check in the process.
    """

    # Arrange
    class _Legacy:
        passed = True
        findings = ()

    check = GateCheck(id="x", stage="pre-submission", run=lambda w, c: _Legacy())
    # Act
    report = _run(tmp_path, check)
    # Assert
    assert (report.blocking, report.outcomes[0].undetermined) == (False, False)
