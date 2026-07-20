"""Unit tests for the shared job log sink (mkdir + rotate + redirect).

This is the helper the 2026-07-19 cron cleanup moved the crontab's inline
shell plumbing into. It is deliberately package-generic so it survives
the migration of the ``_cli.cron`` registry onto the federated
``jobs.JobSpec`` (card dev-two-jobspec-classes-ssot-violation-20260719) —
these tests use plain ``(package, slug)`` strings for that reason, never
a JobSpec of either class.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from scitex_dev.jobs import _logsink


def _fd_identity(fd: int) -> tuple[int, int]:
    """Identify what ``fd`` points at, for restore assertions."""
    st = os.fstat(fd)
    return st.st_ino, st.st_dev


# -- path resolution --------------------------------------------------------


def test_log_path_lands_under_runtime_logs(tmp_path):
    # Arrange
    # Act
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Assert — runtime/ is the mandated regenerable-state layer.
    assert (
        log
        == tmp_path / ".scitex" / "dev" / "runtime" / "logs" / "cron-ci-watch.log"
    )


def test_log_path_never_uses_the_forbidden_flat_logs_dir(tmp_path):
    # Arrange
    # Act
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Assert — the exact directive violated before the cleanup.
    assert "/.scitex/dev/logs/" not in log.as_posix()


def test_log_path_keys_off_the_package_argument(tmp_path):
    # Arrange — scholar-library-sync logs with the state it syncs.
    # Act
    log = _logsink.log_path("scholar", "cron-library-sync", home=tmp_path)
    # Assert
    assert log.parent == tmp_path / ".scitex" / "scholar" / "runtime" / "logs"


def test_log_path_rejects_a_slug_with_a_path_separator(tmp_path):
    # Arrange
    slug = "../../etc/passwd"
    # Act
    # Assert — a slug is a basename; traversal is a bug, not a path.
    with pytest.raises(ValueError):
        _logsink.log_path("dev", slug, home=tmp_path)


def test_log_path_is_pure_and_creates_nothing(tmp_path):
    # Arrange
    # Act
    _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Assert — pure path arithmetic; the sink does the creating.
    assert not (tmp_path / ".scitex").exists()


# -- mkdir ------------------------------------------------------------------


def test_open_log_sink_creates_missing_parent_directories(tmp_path):
    # Arrange — the `mkdir -p` that used to be in the crontab.
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Act
    with _logsink.open_log_sink(log) as fh:
        fh.write("hello\n")
    # Assert
    assert log.parent.is_dir()


def test_open_log_sink_writes_through_to_the_log_file(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Act
    with _logsink.open_log_sink(log) as fh:
        fh.write("hello\n")
    # Assert
    assert log.read_text() == "hello\n"


def test_open_log_sink_appends_rather_than_truncating(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    with _logsink.open_log_sink(log) as fh:
        fh.write("first\n")
    # Act
    with _logsink.open_log_sink(log) as fh:
        fh.write("second\n")
    # Assert — `>>`, not `>`; history must survive a tick.
    assert log.read_text() == "first\nsecond\n"


# -- fail loud --------------------------------------------------------------


def test_open_log_sink_raises_when_log_dir_cannot_be_created(tmp_path):
    # Arrange — a FILE where the runtime dir must go blocks mkdir.
    (tmp_path / ".scitex").write_text("not a directory")
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Act
    # Assert — never silently degrade to unlogged execution.
    with pytest.raises(_logsink.LogSinkError):
        _logsink.open_log_sink(log)


def test_redirect_to_log_raises_when_log_cannot_be_opened(tmp_path):
    # Arrange — a DIRECTORY where the log file must go blocks open().
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    log.parent.mkdir(parents=True)
    log.mkdir()
    # Act
    # Assert
    with pytest.raises(_logsink.LogSinkError):
        with _logsink.redirect_to_log(log):
            pass


def test_log_sink_error_names_the_offending_path(tmp_path):
    # Arrange
    (tmp_path / ".scitex").write_text("not a directory")
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Act
    try:
        _logsink.open_log_sink(log)
        message = ""
    except _logsink.LogSinkError as exc:
        message = str(exc)
    # Assert — an operator must be able to act on the message alone.
    assert ".scitex" in message


# -- rotation ---------------------------------------------------------------


def test_rotate_if_large_reports_that_it_rotated(tmp_path):
    # Arrange
    log = tmp_path / "big.log"
    log.write_text("x" * 200)
    # Act
    rotated = _logsink.rotate_if_large(log, max_bytes=100)
    # Assert
    assert rotated is True


def test_rotate_if_large_moves_an_oversized_log_to_dot_one(tmp_path):
    # Arrange
    log = tmp_path / "big.log"
    log.write_text("x" * 200)
    # Act
    _logsink.rotate_if_large(log, max_bytes=100)
    # Assert
    assert (tmp_path / "big.log.1").read_text() == "x" * 200


def test_rotate_if_large_clears_the_way_for_a_fresh_log(tmp_path):
    # Arrange
    log = tmp_path / "big.log"
    log.write_text("x" * 200)
    # Act
    _logsink.rotate_if_large(log, max_bytes=100)
    # Assert
    assert not log.exists()


def test_rotate_if_large_leaves_a_small_log_alone(tmp_path):
    # Arrange
    log = tmp_path / "small.log"
    log.write_text("x" * 10)
    # Act
    _logsink.rotate_if_large(log, max_bytes=100)
    # Assert
    assert log.read_text() == "x" * 10


def test_rotate_if_large_is_a_noop_on_a_missing_log(tmp_path):
    # Arrange
    absent = tmp_path / "absent.log"
    # Act
    rotated = _logsink.rotate_if_large(absent, max_bytes=100)
    # Assert — a first run has nothing to rotate; that is not an error.
    assert rotated is False


def test_rotation_threshold_is_one_mebibyte():
    # Arrange
    # Act
    threshold = _logsink.LOG_ROTATE_BYTES
    # Assert — inherited from the ad-hoc creds-rotate crontab line this
    # module subsumes, so behaviour matches what the host already had.
    assert threshold == 1_048_576


def test_open_log_sink_rotates_before_opening(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    log.parent.mkdir(parents=True)
    log.write_text("y" * 200)
    # Act
    with _logsink.open_log_sink(log, max_bytes=100) as fh:
        fh.write("fresh\n")
    # Assert — the running job re-opens a fresh file.
    assert log.read_text() == "fresh\n"


def test_open_log_sink_preserves_rotated_history(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    log.parent.mkdir(parents=True)
    log.write_text("y" * 200)
    # Act
    with _logsink.open_log_sink(log, max_bytes=100) as fh:
        fh.write("fresh\n")
    # Assert — rotation must not destroy the previous run's evidence.
    assert (log.parent / "cron-ci-watch.log.1").read_text() == "y" * 200


def test_open_log_sink_can_skip_rotation(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    log.parent.mkdir(parents=True)
    log.write_text("y" * 200)
    # Act
    with _logsink.open_log_sink(log, rotate=False, max_bytes=100) as fh:
        fh.write("more\n")
    # Assert
    assert log.read_text() == "y" * 200 + "more\n"


# -- redirect ---------------------------------------------------------------


def test_redirect_to_log_captures_python_level_stdout(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Act
    with _logsink.redirect_to_log(log):
        print("from python")
        sys.stdout.flush()
    # Assert
    assert "from python" in log.read_text()


def test_redirect_to_log_captures_stderr_too(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Act — the `2>&1` half of the retired crontab plumbing.
    with _logsink.redirect_to_log(log):
        print("to stderr", file=sys.stderr)
        sys.stderr.flush()
    # Assert
    assert "to stderr" in log.read_text()


def test_redirect_to_log_captures_subprocess_stdout(tmp_path):
    # Arrange — the reason redirection is done at the fd level rather
    # than by rebinding sys.stdout: shell-bodied jobs (ssh, rsync, sac)
    # write from CHILD processes, and that output is what operators grep.
    log = _logsink.log_path("dev", "cron-ecosystem-sync", home=tmp_path)
    # Act
    with _logsink.redirect_to_log(log):
        subprocess.run("echo from-a-child", shell=True, check=True)
    # Assert
    assert "from-a-child" in log.read_text()


def test_redirect_to_log_captures_subprocess_stderr(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ecosystem-sync", home=tmp_path)
    # Act
    with _logsink.redirect_to_log(log):
        subprocess.run("echo child-err >&2", shell=True, check=True)
    # Assert
    assert "child-err" in log.read_text()


def test_redirect_to_log_restores_stdout_afterwards(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    before = _fd_identity(1)
    # Act
    with _logsink.redirect_to_log(log):
        pass
    # Assert
    assert _fd_identity(1) == before


def test_redirect_to_log_restores_stderr_afterwards(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    before = _fd_identity(2)
    # Act
    with _logsink.redirect_to_log(log):
        pass
    # Assert
    assert _fd_identity(2) == before


def test_redirect_to_log_restores_stdout_even_on_exception(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    before = _fd_identity(1)
    # Act
    try:
        with _logsink.redirect_to_log(log):
            raise ValueError("job body blew up")
    except ValueError:
        pass
    # Assert — a crashing job must not leave the process's stdout wedged
    # pointing at a closed log.
    assert _fd_identity(1) == before


def test_redirect_to_log_records_output_written_before_an_exception(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Act
    try:
        with _logsink.redirect_to_log(log):
            print("progress so far")
            sys.stdout.flush()
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    # Assert — the log is the only forensic trail a cron failure leaves.
    assert "progress so far" in log.read_text()


def test_redirect_to_log_propagates_the_body_exception(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Act
    # Assert — the sink must not swallow a failing job.
    with pytest.raises(RuntimeError):
        with _logsink.redirect_to_log(log):
            raise RuntimeError("boom")


def test_redirect_to_log_creates_the_directory_it_needs(tmp_path):
    # Arrange
    log = _logsink.log_path("dev", "cron-ci-watch", home=tmp_path)
    # Act
    with _logsink.redirect_to_log(log):
        print("x")
    # Assert
    assert log.is_file()
