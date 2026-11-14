"""Inspect real fixture-owned groups without exposing process arguments."""

import os
import subprocess
from pathlib import Path

import pytest

RESOURCE = Path(__file__).resolve().parents[2] / "src/scitex_dev/ci/owned_context.sh"
SECRET = "must-not-appear-in-group-report"


def execute(tmp_path, body):
    return subprocess.run(
        ["bash", "-c", 'set -euo pipefail; source "$1"; ' + body,
         SECRET, str(RESOURCE), str(tmp_path)],
        env={"PATH": os.defpath, "HOME": str(tmp_path), "PRIVATE_VALUE": SECRET},
        start_new_session=True, capture_output=True, text=True, timeout=15,
    )


@pytest.fixture
def report(tmp_path):
    return execute(tmp_path, 'printf "%s" "$$"; owned_report_group "$$"')


def test_report_identifies_actual_group(report):
    # Arrange
    pid = report.stdout
    # Act
    members = report.stderr.splitlines()
    # Assert
    assert any(f"pid={pid} " in row and f"pgid={pid} " in row for row in members)


def test_report_returns_success_status(report):
    # Arrange
    result = report
    # Act
    status = result.returncode
    # Assert
    assert status == 0


def test_report_contains_only_selected_metadata(report):
    # Arrange
    result = report
    # Act
    rows = [row for row in result.stderr.splitlines() if row.startswith("owned group member:")]
    # Assert
    assert 1 <= len(rows) <= 32 and all("state=" in row and "elapsed_seconds=" in row for row in rows)


def test_report_omits_arguments_and_environment(report):
    # Arrange
    result = report
    # Act
    stderr = result.stderr
    # Assert
    assert SECRET not in stderr and str(RESOURCE) not in stderr


@pytest.fixture
def refusal(tmp_path):
    body = ('owned_context_init "$2" scitex-report-test-; '
            'printf "%s" "$$"; OWNED_CHILD_GROUP=$$; exit 23')
    return execute(tmp_path, body)


def test_refusal_keeps_owned_root_and_status(tmp_path, refusal):
    # Arrange
    result = refusal
    # Act
    outcome = result.returncode, len(list(tmp_path.glob("scitex-report-test-*")))
    # Assert
    assert outcome == (23, 1)


def test_refusal_reports_actual_member(refusal):
    # Arrange
    result = refusal
    # Act
    diagnostic = result.stderr
    # Assert
    assert f"pid={result.stdout} " in diagnostic and "temporary cleanup refused" in diagnostic


def test_refusal_diagnostic_omits_secrets(refusal):
    # Arrange
    result = refusal
    # Act
    diagnostic = result.stderr
    # Assert
    assert SECRET not in diagnostic


@pytest.mark.parametrize("group", ["", "0", "-1", "not-a-group", "12345678901"])
def test_invalid_group_cannot_be_reported(tmp_path, group):
    # Arrange
    body = 'owned_report_group "' + group + '"'
    # Act
    result = execute(tmp_path, body)
    # Assert
    assert (result.returncode, result.stdout, result.stderr) == (1, "", "")


def test_real_group_overflow_reports_only_bounded_members(tmp_path):
    # Arrange
    body = ('for ((i=0;i<40;i++)); do sleep 5 & done; '
            'owned_report_group "$$"; wait')
    # Act
    result = execute(tmp_path, body)
    # Assert
    members = [row for row in result.stderr.splitlines()
               if row.startswith("owned group member:")]
    assert (result.returncode, len(members),
            "owned group report: additional members omitted" in result.stderr) == (0, 32, True)
