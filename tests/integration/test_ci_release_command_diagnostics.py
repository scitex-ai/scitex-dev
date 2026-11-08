"""Real subprocess controls for timeout evidence without weakening deadlines."""

import json
import subprocess
import sys

import pytest

from ._release_command import _LIMIT, _NOTE_PREFIX, _tail, run_release_command


def test_real_timeout_keeps_deadline_and_actual_git_trace(tmp_path):
    # Arrange
    root = tmp_path / "fixture"
    root.mkdir()
    trace = tmp_path / "git-trace.jsonl"
    environment = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/dev/null",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_TRACE2_EVENT": str(trace)}
    run_release_command(["git", "--version"], root, environment, check=True)
    command = [sys.executable, "-I", "-S", "-B", "-c", "import time; time.sleep(30)"]
    observed = None
    # Act
    try:
        run_release_command(command, root, environment, check=True)
    except subprocess.TimeoutExpired as error:
        note = next(note for note in error.__notes__ if note.startswith(_NOTE_PREFIX))
        evidence = json.loads(note[len(_NOTE_PREFIX):])
        events = [json.loads(line) for line in evidence["git_trace_tail"].splitlines()]
        observed = (error.timeout, error.cmd, evidence["timeout_seconds"],
                    any(event.get("name") == "version" for event in events),
                    set(evidence) >= {"observed_utc", "loadavg", "io_pressure", "memory"})
    # Assert
    assert observed == (5, command, 5, True, True)


def test_diagnostic_reads_are_bounded_and_missing_data_is_explicit(tmp_path):
    # Arrange
    trace = tmp_path / "git-trace.jsonl"
    trace.write_bytes(b"discard" + b"x" * _LIMIT)
    # Act
    observed = (_tail(trace), _tail(tmp_path / "absent"))
    # Assert
    assert observed == ("x" * _LIMIT, "unavailable: FileNotFoundError")


@pytest.mark.parametrize("code", [0, 7])
def test_real_exit_status_and_output_remain_visible(tmp_path, code):
    # Arrange
    command = [sys.executable, "-I", "-S", "-B", "-c",
               f"import sys; print('owned output'); sys.exit({code})"]
    # Act
    result = run_release_command(command, tmp_path, {}, text=True, check=False)
    # Assert
    assert (result.returncode, result.stdout, result.stderr) == (code, "owned output\n", "")


def test_check_true_retains_original_nonzero_exception(tmp_path):
    # Arrange
    command = [sys.executable, "-I", "-S", "-B", "-c", "raise SystemExit(7)"]
    # Act
    # Assert
    with pytest.raises(subprocess.CalledProcessError, match="exit status 7"):
        run_release_command(command, tmp_path, {}, check=True)
