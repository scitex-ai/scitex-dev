"""Tests for ``scitex_dev.trace_env.trace`` — the dynamic strace tracer.

Exercises the ``--trace`` engine without needing strace on the box:

* Graceful ``trace_env_vars`` behaviour when strace is missing.
* ``_result_from_trace`` classification of empty / non-empty strace output
  (inconclusive-vs-absent, ptrace-permission hint, exec-stage locate).
* ``_redact_raw_log`` — the persisted strace log carries the FULL env of
  every exec stage; secret-shaped names must be redacted before the log is
  left on disk.
* ``_sanitize_command`` / ``_new_log_path`` — the discoverable ``tail -f``-able
  runtime log path (under ``$SCITEX_DIR/runtime/trace-env-vars/``).

The CLI passthrough (``--trace`` via ``CliRunner``) lives in
``tests/scitex_dev/_cli/test__trace_env.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scitex_dev.trace_env import trace_env_vars
from scitex_dev.trace_env.trace import _result_from_trace


# --------------------------------------------------------------------
# Fixture — empty PATH so shutil.which finds no strace (restore on teardown).
# --------------------------------------------------------------------


@pytest.fixture
def empty_path(tmp_path):
    # Arrange: point PATH at an empty dir so shutil.which finds nothing.
    empty = tmp_path / "emptybin"
    empty.mkdir()
    prior = os.environ.get("PATH")
    os.environ["PATH"] = str(empty)
    yield
    if prior is None:
        os.environ.pop("PATH", None)
    else:
        os.environ["PATH"] = prior


# --------------------------------------------------------------------
# Graceful degradation — strace absence.
# --------------------------------------------------------------------


def test_trace_error_message_when_strace_missing(empty_path):
    # Arrange
    # Act
    result = trace_env_vars(["FOO"], command=["echo", "hi"])
    # Assert
    assert "strace is required" in (result.error or "")


def test_trace_mode_is_trace_when_strace_missing(empty_path):
    # Arrange
    # Act
    result = trace_env_vars(["FOO"], command=["echo", "hi"])
    # Assert
    assert result.mode == "trace"


# --------------------------------------------------------------------
# Empty strace output — inconclusive, NOT "var absent".
# --------------------------------------------------------------------


def test_trace_empty_output_is_inconclusive_not_var_absent():
    # Arrange: strace produced ZERO execve records (ptrace denied).
    # Act
    result = _result_from_trace(["FOO"], raw="", stderr_text="")
    # Assert
    assert "inconclusive" in (result.error or "")


def test_trace_empty_output_disclaims_var_not_found():
    # Arrange
    # Act
    result = _result_from_trace(["FOO"], raw="", stderr_text="")
    # Assert
    assert "not found" in (result.error or "")


def test_trace_empty_output_reports_zero_stages():
    # Arrange
    # Act
    result = _result_from_trace(["FOO"], raw="", stderr_text="")
    # Assert
    assert result.exec_stages == 0


def test_trace_empty_output_has_no_hits():
    # Arrange
    # Act
    result = _result_from_trace(["FOO"], raw="", stderr_text="")
    # Assert
    assert result.trace_hits == []


def test_trace_empty_output_surfaces_ptrace_hint():
    # Arrange
    stderr = "strace: ptrace(PTRACE_TRACEME, ...): Operation not permitted\n"
    # Act
    result = _result_from_trace(["FOO"], raw="", stderr_text=stderr)
    # Assert
    assert "strace said:" in (result.error or "")


def test_trace_nonempty_output_locates_var():
    # Arrange: a synthetic execve record carrying FOO.
    raw = 'execve("/bin/x", ["x"], ["PATH=/bin", "FOO=bar"]) = 0\n'
    # Act
    result = _result_from_trace(["FOO"], raw=raw, stderr_text="")
    # Assert
    assert result.trace_hits[0].var == "FOO"


def test_trace_nonempty_output_has_no_error():
    # Arrange
    raw = 'execve("/bin/x", ["x"], ["FOO=bar"]) = 0\n'
    # Act
    result = _result_from_trace(["FOO"], raw=raw, stderr_text="")
    # Assert
    assert result.error is None


def test_trace_nonempty_but_var_absent_is_not_inconclusive():
    # Arrange: strace worked (a stage parsed) but FOO is not in it.
    raw = 'execve("/bin/x", ["x"], ["PATH=/bin"]) = 0\n'
    # Act
    result = _result_from_trace(["FOO"], raw=raw, stderr_text="")
    # Assert
    assert result.error is None


# --------------------------------------------------------------------
# Raw-log redaction — the persisted strace log carries the FULL env of
# every exec stage, not just the traced var; secret-shaped names must
# be redacted before that log is left on disk at a discoverable path.
# --------------------------------------------------------------------


def test_redact_raw_log_redacts_secret_shaped_envp_value():
    # Arrange
    from scitex_dev.trace_env.trace import _redact_raw_log

    raw = 'execve("/bin/x", ["x"], ["AWS_SECRET_ACCESS_KEY=abcdef1234"]) = 0\n'
    # Act
    redacted = _redact_raw_log(raw)
    # Assert
    assert "abcdef1234" not in redacted


def test_redact_raw_log_keeps_secret_var_name_visible():
    # Arrange
    from scitex_dev.trace_env.trace import _redact_raw_log

    raw = 'execve("/bin/x", ["x"], ["AWS_SECRET_ACCESS_KEY=abcdef1234"]) = 0\n'
    # Act
    redacted = _redact_raw_log(raw)
    # Assert
    assert "AWS_SECRET_ACCESS_KEY=<redacted: 10 chars>" in redacted


def test_redact_raw_log_leaves_non_secret_value_untouched():
    # Arrange
    from scitex_dev.trace_env.trace import _redact_raw_log

    raw = 'execve("/bin/x", ["x"], ["PATH=/usr/bin"]) = 0\n'
    # Act
    redacted = _redact_raw_log(raw)
    # Assert
    assert "PATH=/usr/bin" in redacted


def test_redact_raw_log_redacts_secret_shaped_argv_token():
    # Arrange: `env API_TOKEN=x cmd`-style inline assignment in argv,
    # not just envp — the redaction walks every quoted string in the
    # line, so this NAME=VALUE token gets caught the same way.
    from scitex_dev.trace_env.trace import _redact_raw_log

    raw = 'execve("/bin/x", ["x", "API_TOKEN=supersecret"], ["PATH=/bin"]) = 0\n'
    # Act
    redacted = _redact_raw_log(raw)
    # Assert
    assert "supersecret" not in redacted


def test_redact_raw_log_does_not_crash_on_malformed_quotes():
    # Arrange: an unterminated quote (truncated strace line).
    from scitex_dev.trace_env.trace import _redact_raw_log

    raw = 'execve("/bin/x", ["x"], ["FOO=bar\n'
    # Act
    redacted = _redact_raw_log(raw)
    # Assert
    assert isinstance(redacted, str)


# --------------------------------------------------------------------
# Live-log path — discoverable ``tail -f``-able runtime log, not an
# anonymous /tmp tempfile (operator ask: surface a live-progress hint
# for long-running multi-stage --trace launches).
# --------------------------------------------------------------------


def test_sanitize_command_joins_with_single_delimiter():
    # Arrange
    from scitex_dev.trace_env.trace import _sanitize_command

    # Act
    result = _sanitize_command(["sac", "agents", "start", "scitex-todo", "--yes"])
    # Assert
    assert result == "sac-agents-start-scitex-todo-yes"


def test_sanitize_command_drops_bare_dashdash():
    # Arrange
    from scitex_dev.trace_env.trace import _sanitize_command

    # Act
    result = _sanitize_command(["echo", "--", "hi"])
    # Assert
    assert result == "echo-hi"


def test_sanitize_command_never_empty():
    # Arrange
    from scitex_dev.trace_env.trace import _sanitize_command

    # Act
    result = _sanitize_command([])
    # Assert
    assert result == "cmd"


def test_sanitize_command_is_length_capped():
    # Arrange
    from scitex_dev.trace_env.trace import _sanitize_command

    # Act
    result = _sanitize_command(["x" * 500])
    # Assert
    assert len(result) <= 80


def test_new_log_path_is_under_trace_env_vars_dir():
    # Arrange
    from scitex_dev.trace_env.trace import _new_log_path

    # Act
    log_path = _new_log_path(["echo", "hi"])
    # Assert
    assert log_path.parent.name == "trace-env-vars"


def test_new_log_path_is_under_runtime_dir():
    # Arrange
    from scitex_dev.trace_env.trace import _new_log_path

    # Act
    log_path = _new_log_path(["echo", "hi"])
    # Assert
    assert log_path.parent.parent.name == "runtime"


def test_new_log_path_ignores_project_scope_git_repo(tmp_path):
    # Arrange: fake a project-scope `.scitex/dev/` inside a git repo, and
    # point $SCITEX_DIR at a separate fixed location. The log must land
    # under $SCITEX_DIR regardless of the project-scope dir's presence —
    # this diagnostic tool must never scatter logs into whichever repo
    # the operator happens to be standing in.
    from scitex_dev.trace_env.trace import _new_log_path

    project = tmp_path / "some-repo"
    (project / ".git").mkdir(parents=True)
    (project / ".scitex" / "dev").mkdir(parents=True)
    fixed_home = tmp_path / "fixed-scitex-home"
    prior_cwd = Path.cwd()
    prior_scitex_dir = os.environ.get("SCITEX_DIR")
    os.chdir(project)
    os.environ["SCITEX_DIR"] = str(fixed_home)
    # Act
    try:
        log_path = _new_log_path(["echo", "hi"])
    finally:
        os.chdir(prior_cwd)
        if prior_scitex_dir is None:
            os.environ.pop("SCITEX_DIR", None)
        else:
            os.environ["SCITEX_DIR"] = prior_scitex_dir
    # Assert
    assert str(log_path).startswith(str(fixed_home))


def test_new_log_path_filename_carries_sanitized_command():
    # Arrange
    from scitex_dev.trace_env.trace import _new_log_path

    # Act
    log_path = _new_log_path(["echo", "hi"])
    # Assert
    assert "echo-hi" in log_path.name
