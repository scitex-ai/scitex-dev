"""Real Git controls for evidence added to inner fixture commands."""

import json
import os
import subprocess

from ._git_fixture_command import NOTE_PREFIX, run_fixture_command


def _environment(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _outcome(command, root, environment):
    try:
        return run_fixture_command(command, root, environment, timeout=3)
    except subprocess.SubprocessError as error:
        return error


def test_successful_git_command_preserves_result_and_source(tmp_path):
    # Arrange
    root = tmp_path / "owned repository"
    root.mkdir()
    kept = root / "kept.txt"
    kept.write_text("unrelated fixture source\n")
    environment = _environment(tmp_path)
    before = dict(environment)
    # Act
    result = run_fixture_command(
        ["git", "-C", str(root), "init", "-q"], root, environment, timeout=3
    )
    # Assert
    assert (
        result.returncode,
        result.stdout,
        result.stderr,
        kept.read_text(),
        environment == before,
        list(tmp_path.glob("git-fixture-trace-*")),
    ) == (0, "", "", "unrelated fixture source\n", True, [])


def test_git_timeout_retains_original_deadline_and_actual_trace(tmp_path, capsys):
    # Arrange
    root = tmp_path / "owned repository"
    root.mkdir()
    environment = _environment(tmp_path)
    run_fixture_command(
        ["git", "-C", str(root), "init", "-q"], root, environment, timeout=3
    )
    command = [
        "git",
        "-C",
        str(root),
        "-c",
        "alias.fixture-wait=!sleep 4",
        "fixture-wait",
    ]
    # Act
    outcome = _outcome(command, root, environment)
    messages = [*getattr(outcome, "__notes__", []), capsys.readouterr().err]
    note = next(
        line
        for message in messages
        for line in message.splitlines()
        if line.startswith(NOTE_PREFIX)
    )
    evidence = json.loads(note.removeprefix(NOTE_PREFIX))
    # Assert
    assert (
        type(outcome),
        outcome.cmd,
        outcome.timeout,
        evidence["timeout_seconds"],
        evidence["command"],
        '"event":"child_start"' in evidence["git_trace_tail"],
        len(evidence["git_trace_tail"].encode()) <= 8192,
        evidence["owned_child_observation"]["collector_stopped"],
    ) == (subprocess.TimeoutExpired, command, 3, 3, command, True, True, True)


def test_failed_git_command_keeps_original_exit_and_error(tmp_path):
    # Arrange
    root = tmp_path / "owned repository"
    root.mkdir()
    environment = _environment(tmp_path)
    command = ["git", "-C", str(root), "definitely-not-a-git-command"]
    # Act
    outcome = _outcome(command, root, environment)
    # Assert
    assert (
        type(outcome),
        outcome.cmd,
        outcome.returncode,
        "not a git command" in outcome.stderr,
    ) == (subprocess.CalledProcessError, command, 1, True)
