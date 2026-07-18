"""Tests for ``scitex-dev cron exec`` — the verb that owns its logging.

Exercised through a real shell-bodied job (``ci-runner-ensure``) with
``$HOME`` pointed at a tmp dir, so these cover the whole chain the
crontab used to spell out inline: mkdir -p, the redirect, and the
subprocess output landing in the file.
"""

from __future__ import annotations

import os

import click
import pytest

from scitex_dev._cli.cron import _job_commands
from scitex_dev._cli.cron.run import _run_body


@pytest.fixture()
def fake_home(tmp_path):
    """Point ``Path.home()`` at a tmp dir by setting the real $HOME.

    Real environment mutation with real teardown — no monkeypatch, so
    the code under test resolves its paths exactly as it does in
    production.
    """
    saved = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        yield tmp_path
    finally:
        if saved is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = saved


def _exec_with_log(name: str, home) -> "object":
    """Run a job body under its log sink, exactly as `cron exec` does."""
    from scitex_dev.jobs._logsink import redirect_to_log

    log = _job_commands.log_path_for(name)
    with redirect_to_log(log):
        code = _run_body(name, only=None, dry_run=False)
    return log, code


# -- the verb creates its own log ------------------------------------------


def test_exec_creates_the_log_directory(fake_home):
    # Arrange — the `mkdir -p` retired from the crontab line.
    # Act
    log, _ = _exec_with_log("ci-runner-ensure", fake_home)
    # Assert
    assert log.parent.is_dir()


def test_exec_creates_the_log_file(fake_home):
    # Arrange
    # Act
    log, _ = _exec_with_log("ci-runner-ensure", fake_home)
    # Assert
    assert log.is_file()


def test_exec_log_lands_under_runtime_logs(fake_home):
    # Arrange
    # Act
    log, _ = _exec_with_log("ci-runner-ensure", fake_home)
    # Assert
    assert log.parent == fake_home / ".scitex" / "dev" / "runtime" / "logs"


def test_exec_captures_subprocess_stderr_into_the_log(fake_home):
    # Arrange — the host script does not exist under the fake HOME, so
    # the shell writes a diagnostic naming it. That message is exactly
    # the kind of output an operator greps for, and it comes from a
    # CHILD process — which is why the redirect is fd-level.
    # Act
    log, _ = _exec_with_log("ci-runner-ensure", fake_home)
    # Assert — match the SCRIPT NAME, not the diagnostic wording: dash
    # says "not found" while bash says "No such file or directory", and
    # /bin/sh is one or the other depending on the host. Every shell
    # names the command it could not run.
    assert "ci-runner-ensure-cron.sh" in log.read_text()


def test_exec_propagates_the_bodys_exit_code(fake_home):
    # Arrange — a missing command is 127 from the shell.
    # Act
    _, code = _exec_with_log("ci-runner-ensure", fake_home)
    # Assert — a failing job must not be reported as a clean run.
    assert code == 127


def test_exec_expands_home_in_the_shell_payload(fake_home):
    # Arrange — proves $HOME (not ~) is what reaches /bin/sh: the
    # diagnostic names the EXPANDED tmp path, so expansion happened.
    # Act
    log, _ = _exec_with_log("ci-runner-ensure", fake_home)
    # Assert
    assert str(fake_home) in log.read_text()


# -- fail loud --------------------------------------------------------------


def test_exec_raises_when_the_log_dir_cannot_be_created(fake_home):
    # Arrange — a FILE where the runtime tree must go.
    (fake_home / ".scitex").write_text("not a directory")
    # Act
    # Assert — never silently degrade to unlogged execution.
    with pytest.raises(Exception):
        _exec_with_log("ci-runner-ensure", fake_home)


# -- dispatch coverage ------------------------------------------------------


def test_unhandled_job_name_fails_loudly():
    # Arrange — a registry entry with no body would otherwise no-op.
    # Act
    # Assert
    with pytest.raises(click.ClickException):
        _run_body("not-a-registered-job", only=None, dry_run=False)


def test_shell_bodied_jobs_are_dispatched_before_the_python_branches():
    # Arrange
    # Act — every JOB_SHELL_BODIES key must be reachable, i.e. none may
    # collide with a Python-bodied name and be shadowed.
    python_bodied = {
        "ci-watch",
        "quota-keepalive",
        "worktree-gc",
        "task-harvest",
        "cred-distribute",
        "spartan-conn-monitor",
    }
    collisions = python_bodied & set(_job_commands.JOB_SHELL_BODIES)
    # Assert
    assert collisions == set()
