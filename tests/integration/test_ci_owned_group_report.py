"""Inspect real fixture-owned groups without exposing process arguments."""

import os
import signal
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


@pytest.fixture(params=[False, True], ids=["term", "kill"])
def timed_out_report(tmp_path, request):
    """Exercise GNU timeout against a real, fixture-owned blocked collector."""
    worker = tmp_path / "blocked-collector"
    ready = tmp_path / "collector.pid"
    worker.write_text('''#!/bin/bash
set -eu
pid=$BASHPID
IFS= read -r statline < "/proc/$pid/stat"
statline="${statline##*) }"
set -- $statline
printf '%s %s' "$pid" "${20}" > "$HOME/collector.pid"
if [[ "$COLLECTOR_IGNORE_TERM" == 1 ]]; then trap '' TERM; fi
exec /usr/bin/sleep 30
''')
    worker.chmod(0o700)
    body = r'''function /usr/bin/timeout() {
    [[ "$#" == 6 && "$1" == --signal=TERM && "$2" == --kill-after=1s &&
       "$3" == 1s && "$4" == /usr/bin/ps && "$5" == -eo &&
       "$6" == pid=,ppid=,pgid=,sid=,stat=,etimes= ]] || return 99
    command /usr/bin/timeout "$1" "$2" "$3" "$HOME/blocked-collector"
}
export COLLECTOR_IGNORE_TERM=''' + str(int(request.param)) + '\nowned_report_group "$$"'
    identity = None
    try:
        result = execute(tmp_path, body)
        identity = tuple(ready.read_text().split())
        yield result, (137 if request.param else 124), identity
    finally:
        if identity is None and ready.exists():
            identity = tuple(ready.read_text().split())
        if identity is not None:
            pid, token = identity
            status = Path(f"/proc/{pid}/stat")
            try:
                current = status.read_text().rsplit(") ", 1)[1].split()
                if current[19] == token and current[0] != "Z":
                    os.kill(int(pid), signal.SIGKILL)
            except (FileNotFoundError, ProcessLookupError):
                pass


def test_collector_timeout_preserves_actual_failure_status(timed_out_report):
    # Arrange
    result, expected, _ = timed_out_report
    # Act
    observed = result.returncode, f"collection failed (status={expected})" in result.stderr
    # Assert
    assert observed == (expected, True)


def test_collector_timeout_diagnostic_omits_arguments_and_environment(timed_out_report):
    # Arrange
    result, _, _ = timed_out_report
    # Act
    output = result.stdout + result.stderr
    # Assert
    assert SECRET not in output and str(RESOURCE) not in output


def test_collector_timeout_stops_the_owned_worker(timed_out_report):
    # Arrange
    _, _, (pid, token) = timed_out_report
    # Act
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        alive = state[19] == token and state[0] != "Z"
    except (FileNotFoundError, ProcessLookupError):
        alive = False
    # Assert
    assert not alive
