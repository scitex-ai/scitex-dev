"""Exercise real child processes; these are not PostgreSQL qualification tests."""

import subprocess
import sys

from scitex_dev.store._testing_process import _run_bootstrap


def _observe(command, *, timeout=120):
    """Return the real subprocess outcome so each test asserts one contract."""
    try:
        return _run_bootstrap(command, stage="owned process", timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        return error


def test_success_preserves_captured_output():
    # Arrange
    command = [sys.executable, "-c", "import sys;sys.stdout.write('ready')"]
    # Act
    result = _run_bootstrap(command, stage="owned process")
    # Assert
    assert (result.returncode, result.stdout, result.stderr) == (0, "ready", "")


def test_failed_process_keeps_its_status_and_output():
    # Arrange
    command = [sys.executable, "-c",
               "import sys;sys.stdout.write('before');sys.stderr.write('reason');sys.exit(7)"]
    # Act
    result = _observe(command)
    # Assert
    assert (type(result), result.returncode, result.stdout,
            result.stderr) == (subprocess.CalledProcessError, 7, "before", "reason")


def test_failure_logs_the_stage_and_both_captured_streams(capfd):
    # Arrange
    command = [sys.executable, "-c",
               "import sys;sys.stdout.write('before');sys.stderr.write('reason');sys.exit(7)"]
    # Act
    _observe(command)
    captured = capfd.readouterr()
    output = captured.out + captured.err
    # Assert
    assert all(text in output for text in
               ["owned process", "CalledProcessError", "before", "reason"])


def test_failure_does_not_retry_the_child(tmp_path):
    # Arrange
    counter = tmp_path / "attempts"
    command = [sys.executable, "-c",
               "import pathlib,sys;p=pathlib.Path(sys.argv[1]);"
               "p.write_text(p.read_text()+'x' if p.exists() else 'x');sys.exit(7)",
               str(counter)]
    # Act
    _observe(command)
    # Assert
    assert counter.read_text() == "x"


def test_timeout_preserves_the_caller_budget_and_captured_bytes():
    # Arrange
    command = [sys.executable, "-c",
               "import sys,time;sys.stdout.write('started');sys.stdout.flush();time.sleep(10)"]
    # Act
    result = _observe(command, timeout=2)
    # Assert
    assert (type(result), result.timeout, result.stdout) == (
        subprocess.TimeoutExpired, 2, b"started")


def test_timeout_logs_progress_before_preserving_the_failure(capfd):
    # Arrange
    command = [sys.executable, "-c",
               "import sys,time;sys.stdout.write('startup-stage');sys.stdout.flush();time.sleep(10)"]
    # Act
    _observe(command, timeout=2)
    captured = capfd.readouterr()
    output = captured.out + captured.err
    # Assert
    assert "TimeoutExpired" in output and "startup-stage" in output


def test_output_tail_is_bounded_and_control_characters_are_escaped(capfd):
    # Arrange
    command = [sys.executable, "-c",
               "import sys;sys.stdout.write('discard-prefix'+'x'*5000+'\\x1b[2Jtail');sys.exit(7)"]
    # Act
    _observe(command)
    captured = capfd.readouterr()
    output = captured.out + captured.err
    # Assert
    assert ("discard-prefix" in output, "\\x1b[2Jtail" in output,
            len(output) < 3000) == (False, True, True)
