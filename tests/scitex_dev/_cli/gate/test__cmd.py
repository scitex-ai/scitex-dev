"""Tests for the ``scitex-dev gate`` CLI command (exit codes + JSON shape)."""

from __future__ import annotations

import json
import tempfile

from click.testing import CliRunner

from scitex_dev._cli._root import main


def test_gate_passes_on_existing_workdir_exit_zero():
    # Arrange
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as td:
        # Act
        res = runner.invoke(main, ["gate", "--stage=pre-submission", td, "--json"])
    # Assert
    assert res.exit_code == 0


def test_gate_json_reports_not_blocking_on_pass():
    # Arrange
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as td:
        # Act
        res = runner.invoke(main, ["gate", "--stage=pre-submission", td, "--json"])
        payload = json.loads(res.output.splitlines()[-1])
    # Assert
    assert payload["blocking"] is False


def test_gate_warn_default_missing_dir_exit_zero():
    # Arrange — builtin fails but is unenforced (no config) → advisory.
    runner = CliRunner()
    # Act
    res = runner.invoke(main, ["gate", "--stage=pre-submission", "/no/such/dir"])
    # Assert
    assert res.exit_code == 0


def test_gate_enforced_missing_dir_exit_two():
    # Arrange — config in the workdir tree enforces the builtin.
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as td:
        import os
        from pathlib import Path

        cfgdir = Path(td) / ".scitex" / "dev"
        cfgdir.mkdir(parents=True)
        (cfgdir / "config.yaml").write_text(
            "gate:\n  enforce: [gate-workdir-present]\n", encoding="utf-8"
        )
        missing = Path(td) / "nope"
        # Act
        res = runner.invoke(
            main, ["gate", "--stage=pre-submission", str(missing)]
        )
    # Assert — enforced failure blocks with exit 2.
    assert res.exit_code == 2


def test_gate_list_needs_no_workdir():
    # Arrange
    runner = CliRunner()
    # Act
    res = runner.invoke(main, ["gate", "--stage=pre-submission", "--list"])
    # Assert
    assert res.exit_code == 0


def test_gate_list_json_includes_builtin():
    # Arrange
    runner = CliRunner()
    # Act
    res = runner.invoke(
        main, ["gate", "--stage=pre-submission", "--list", "--json"]
    )
    ids = [c["id"] for c in json.loads(res.output.splitlines()[-1])]
    # Assert
    assert "gate-workdir-present" in ids


def test_gate_missing_workdir_without_list_is_usage_error():
    # Arrange
    runner = CliRunner()
    # Act
    res = runner.invoke(main, ["gate", "--stage=pre-submission"])
    # Assert — Click usage error exits 2 (missing required WORKDIR).
    assert res.exit_code == 2


def _render_lines(report) -> list[str]:
    """Render ``report`` via the real CLI renderer, return stdout lines.

    Shared test helper (not a test itself) — exercises the exact
    ``_render_human`` code path the CLI uses, without needing a real
    workdir or real registered checks.
    """
    import io
    from contextlib import redirect_stdout

    from scitex_dev._cli.gate._cmd import _render_human

    buf = io.StringIO()
    with redirect_stdout(buf):
        _render_human(report)
    return buf.getvalue().splitlines()


def _unenforced_failure_report():
    """A report shaped exactly like the reported bug: one check ran,
    FAILED, and is NOT enforced — advisory-only, must not block."""
    from scitex_dev.gate import CheckOutcome, Finding, GateReport

    outcome = CheckOutcome(
        id="clew-source-reachability",
        stage="pre-submission",
        ran=True,
        passed=False,
        enforced=False,
        findings=(
            Finding(
                check_id="clew-source-reachability",
                kind="runs_zero",
                message="clew DB has 0 tracked runs",
                severity="error",
                fix_hint="wrap analysis in @stx.session then resubmit",
            ),
        ),
    )
    return GateReport(
        stage="pre-submission", workdir="/some/capsule", outcomes=(outcome,)
    )


def _enforced_failure_report():
    """A report where the same check id is ENFORCED — a real blocking
    failure, the invariant's other side."""
    from scitex_dev.gate import CheckOutcome, GateReport

    outcome = CheckOutcome(
        id="clew-source-reachability",
        stage="pre-submission",
        ran=True,
        passed=False,
        enforced=True,
        findings=(),
    )
    return GateReport(
        stage="pre-submission", workdir="/some/capsule", outcomes=(outcome,)
    )


def _mixed_outcomes_report():
    """One report covering every outcome shape ``run_gate`` can produce:
    passing, advisory-failing (unenforced), and skipped — none enforced,
    so the report as a whole must stay non-blocking."""
    from scitex_dev.gate import CheckOutcome, GateReport

    outcomes = (
        CheckOutcome(
            id="ok-check",
            stage="pre-submission",
            ran=True,
            passed=True,
            enforced=False,
            findings=(),
        ),
        CheckOutcome(
            id="advisory-fail-check",
            stage="pre-submission",
            ran=True,
            passed=False,
            enforced=False,
            findings=(),
        ),
        CheckOutcome(
            id="skipped-check",
            stage="pre-submission",
            ran=False,
            passed=None,
            enforced=False,
            findings=(),
            skipped_reason="disabled",
        ),
    )
    return GateReport(
        stage="pre-submission", workdir="/some/capsule", outcomes=outcomes
    )


def test_gate_unenforced_missing_dir_exit_zero_on_human_render():
    # Arrange — a tool/library repo (like scitex-writer) with NO
    # `.scitex/dev/config.yaml` `gate.enforce` entry: `gate-workdir-present`
    # fails intrinsically (missing dir) — the reported bug's exact shape
    # (`clew-source-reachability: fail` printed under a PASS banner).
    runner = CliRunner()
    # Act — human-readable (non-JSON) render, no config anywhere → advisory.
    res = runner.invoke(main, ["gate", "--stage=pre-submission", "/no/such/dir"])
    # Assert
    assert res.exit_code == 0


def test_gate_unenforced_missing_dir_banner_reads_pass():
    # Arrange
    runner = CliRunner()
    # Act
    res = runner.invoke(main, ["gate", "--stage=pre-submission", "/no/such/dir"])
    banner = res.output.splitlines()[0]
    # Assert
    assert "PASS" in banner


def test_gate_unenforced_missing_dir_check_line_has_no_bare_fail_tag():
    # Arrange
    runner = CliRunner()
    # Act
    res = runner.invoke(main, ["gate", "--stage=pre-submission", "/no/such/dir"])
    check_line = next(
        line for line in res.output.splitlines() if "gate-workdir-present" in line
    )
    # Assert — the bare word "fail" reads as "this failed the gate", which
    # would contradict the PASS banner + exit 0 above.
    assert "fail" not in check_line


def test_gate_unenforced_missing_dir_check_line_reads_warning():
    # Arrange
    runner = CliRunner()
    # Act
    res = runner.invoke(main, ["gate", "--stage=pre-submission", "/no/such/dir"])
    check_line = next(
        line for line in res.output.splitlines() if "gate-workdir-present" in line
    )
    # Assert
    assert "warning" in check_line


def test_gate_render_human_advisory_failure_is_not_blocking():
    # Arrange
    report = _unenforced_failure_report()
    # Act — blocking is computed lazily from outcomes; no render needed.
    is_blocking = report.blocking
    # Assert — an unenforced failure is advisory-only, never blocks.
    assert is_blocking is False


def test_gate_render_human_advisory_failure_banner_reads_pass():
    # Arrange
    report = _unenforced_failure_report()
    # Act
    lines = _render_lines(report)
    # Assert
    assert "PASS" in lines[0]


def test_gate_render_human_advisory_failure_line_has_no_bare_fail_tag():
    # Arrange
    report = _unenforced_failure_report()
    # Act
    lines = _render_lines(report)
    check_line = next(line for line in lines if "clew-source-reachability" in line)
    # Assert — this is the reported bug: a bare "fail" tag under PASS.
    assert "fail" not in check_line


def test_gate_render_human_advisory_failure_line_reads_warning():
    # Arrange
    report = _unenforced_failure_report()
    # Act
    lines = _render_lines(report)
    check_line = next(line for line in lines if "clew-source-reachability" in line)
    # Assert
    assert "warning" in check_line


def test_gate_render_human_enforced_failure_is_blocking():
    # Arrange
    report = _enforced_failure_report()
    # Act
    is_blocking = report.blocking
    # Assert — a real (enforced) failure always flips the gate to BLOCK.
    assert is_blocking is True


def test_gate_render_human_enforced_failure_banner_reads_block():
    # Arrange
    report = _enforced_failure_report()
    # Act
    lines = _render_lines(report)
    # Assert
    assert "BLOCK" in lines[0]


def test_gate_render_human_enforced_failure_line_reads_block():
    # Arrange
    report = _enforced_failure_report()
    # Act
    lines = _render_lines(report)
    check_line = next(line for line in lines if "clew-source-reachability" in line)
    # Assert
    assert "BLOCK" in check_line


def test_gate_mixed_outcomes_report_is_not_blocking():
    # Arrange — the general contract check (not specific to any one check
    # id): a report with passing, advisory-failing, and skipped outcomes,
    # none enforced, must stay non-blocking overall.
    report = _mixed_outcomes_report()
    # Act
    is_blocking = report.blocking
    # Assert
    assert is_blocking is False


def test_gate_mixed_outcomes_no_line_carries_bare_fail_tag():
    # Arrange — the general invariant: no individual check line may ever
    # read a bare "fail" while the overall report is not blocking.
    report = _mixed_outcomes_report()
    # Act
    lines = _render_lines(report)
    check_lines = lines[1:]  # skip the banner line
    # Assert
    assert all(": fail" not in line for line in check_lines)
