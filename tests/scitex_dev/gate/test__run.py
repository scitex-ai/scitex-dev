"""Tests for the submission-gate runner + enforcement overlay.

No mocks — real temp workdirs + injected in-process providers (the
``extra_providers`` seam), so the config-driven warn-default / enforce
semantics are exercised end-to-end.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from scitex_dev.gate import (
    Finding,
    GateCheck,
    GateConfig,
    GateResult,
    report_to_dict,
    run_gate,
)


def _failing_provider(check_id="clew-source-reachability"):
    def run(workdir, config):
        return GateResult(
            passed=False,
            findings=(
                Finding(
                    check_id=check_id,
                    kind="runs_zero",
                    message="clew DB has claims but runs=0",
                    severity="error",
                    fix_hint="wrap analysis in @stx.session then resubmit",
                ),
            ),
        )

    def provide():
        return [GateCheck(check_id, "pre-submission", run, description="x")]

    return provide


def _passing_provider(check_id="always-ok"):
    def run(workdir, config):
        return GateResult(passed=True)

    def provide():
        return [GateCheck(check_id, "pre-submission", run, description="x")]

    return provide


def test_builtin_passes_on_existing_workdir():
    # Arrange
    with tempfile.TemporaryDirectory() as td:
        # Act
        report = run_gate(td, "pre-submission", include_entry_points=False)
        # Assert
        assert report.passed is True


def test_builtin_fails_on_missing_workdir():
    # Arrange
    missing = "/no/such/dir"
    # Act
    report = run_gate(missing, "pre-submission", include_entry_points=False)
    # Assert — the check FAILED intrinsically...
    assert report.outcomes[0].passed is False


def test_unenforced_failure_is_advisory_not_blocking():
    # Arrange — warn-default: no enforce set.
    cfg = GateConfig()
    # Act
    report = run_gate(
        "/no/such/dir", "pre-submission", config=cfg, include_entry_points=False
    )
    # Assert — ...but with no enforce knob, it does NOT block (exit 0).
    assert report.blocking is False


def test_enforced_failure_blocks():
    # Arrange — enforce the builtin.
    cfg = GateConfig(enforce=frozenset({"gate-workdir-present"}))
    # Act
    report = run_gate(
        "/no/such/dir", "pre-submission", config=cfg, include_entry_points=False
    )
    # Assert
    assert report.blocking is True


def test_enforced_plugin_failure_surfaces_fix_hint():
    # Arrange — a clew-like enforced failing check.
    cfg = GateConfig(enforce=frozenset({"clew-source-reachability"}))
    with tempfile.TemporaryDirectory() as td:
        # Act
        report = run_gate(
            td,
            "pre-submission",
            config=cfg,
            extra_providers=[_failing_provider()],
            include_entry_points=False,
        )
        payload = report_to_dict(report)
    # Assert
    hints = [
        f["fix_hint"]
        for c in payload["checks"]
        for f in c["findings"]
        if f["fix_hint"]
    ]
    assert "wrap analysis in @stx.session then resubmit" in hints


def test_disabled_check_is_skipped():
    # Arrange
    cfg = GateConfig(disable=frozenset({"gate-workdir-present"}))
    # Act
    report = run_gate(
        "/no/such/dir", "pre-submission", config=cfg, include_entry_points=False
    )
    # Assert
    assert report.outcomes[0].ran is False


def test_crashing_check_fails_closed():
    # Arrange — a check that raises must FAIL, never silently pass.
    def boom_provide():
        def run(w, c):
            raise RuntimeError("kaboom")

        return [GateCheck("boom", "pre-submission", run)]

    cfg = GateConfig(enforce=frozenset({"boom"}))
    with tempfile.TemporaryDirectory() as td:
        # Act
        report = run_gate(
            td,
            "pre-submission",
            config=cfg,
            extra_providers=[boom_provide],
            include_entry_points=False,
        )
    # Assert
    boom = [o for o in report.outcomes if o.id == "boom"][0]
    assert boom.passed is False and report.blocking is True


def test_crashing_check_emits_check_crashed_finding():
    # Arrange
    def boom_provide():
        def run(w, c):
            raise RuntimeError("kaboom")

        return [GateCheck("boom", "pre-submission", run)]

    with tempfile.TemporaryDirectory() as td:
        # Act
        report = run_gate(
            td,
            "pre-submission",
            extra_providers=[boom_provide],
            include_entry_points=False,
        )
    # Assert
    boom = [o for o in report.outcomes if o.id == "boom"][0]
    assert boom.findings[0].kind == "check_crashed"


def test_requires_missing_module_skips_check():
    # Arrange — a check requiring an unimportable module.
    def prov():
        return [
            GateCheck(
                "needs-ghost",
                "pre-submission",
                lambda w, c: GateResult(passed=True),
                requires="a_module_that_does_not_exist_xyz",
            )
        ]

    with tempfile.TemporaryDirectory() as td:
        # Act
        report = run_gate(
            td, "pre-submission", extra_providers=[prov], include_entry_points=False
        )
    # Assert
    ghost = [o for o in report.outcomes if o.id == "needs-ghost"][0]
    assert ghost.ran is False and "not importable" in ghost.skipped_reason


def test_stage_filter_excludes_other_stage_checks():
    # Arrange — a post-submission-only check must not run at pre-submission.
    def prov():
        return [
            GateCheck(
                "post-only",
                "post-submission",
                lambda w, c: GateResult(passed=True),
            )
        ]

    with tempfile.TemporaryDirectory() as td:
        # Act
        report = run_gate(
            td, "pre-submission", extra_providers=[prov], include_entry_points=False
        )
    # Assert
    assert "post-only" not in [o.id for o in report.outcomes]


def test_passing_plugin_keeps_gate_green():
    # Arrange
    cfg = GateConfig(enforce=frozenset({"always-ok"}))
    with tempfile.TemporaryDirectory() as td:
        # Act
        report = run_gate(
            td,
            "pre-submission",
            config=cfg,
            extra_providers=[_passing_provider()],
            include_entry_points=False,
        )
    # Assert
    assert report.blocking is False
