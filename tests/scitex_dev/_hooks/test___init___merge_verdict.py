#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_hooks/test___init___merge_verdict.py

"""Tests for the shipped merge-gate hook, ``require_mergeable_verdict.sh``.

Named alongside ``test___init___pre_push.py``: one file per shipped hook.

The path test is the cheap half. The half that matters RUNS THE SHELL SCRIPT
against a stubbed ``scitex-dev`` and asserts BOTH directions -- that it blocks
when the verdict says so, and that it lets a ready pull request through. A
gate only proven to pass is a thermometer in a sealed box; a gate only proven
to block is one nobody will keep installed.

No mocks: every case builds a real temp directory, writes a real executable
stub onto PATH, and runs the real script in a real subprocess.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys

import pytest

from scitex_dev._hooks import require_mergeable_verdict_sh_path

# The contract under test, mirrored from scitex_dev.ci._exit_codes.
READY, NOT_READY, CANNOT_DETERMINE, USAGE, UNRECOGNISED = 0, 10, 11, 2, 42

ALLOW, DENY = 0, 2  # the HOOK's own protocol with the harness

MERGE_CMD = "gh pr merge 123 --squash"


def _payload(command: str) -> str:
    return json.dumps({"tool_input": {"command": command}})


def _stub_scitex_dev(bin_dir, exit_code: int) -> None:
    """Write an executable ``scitex-dev`` that exits with ``exit_code``."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "scitex-dev"
    stub.write_text(f'#!/usr/bin/env bash\necho "stub verdict"\nexit {exit_code}\n')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)


def _run_hook(tmp_path, command: str, verdict_exit, payload: str | None = None):
    """Run the packaged hook with ``command``, stubbing the checker.

    ``verdict_exit=None`` means a PATH deliberately WITHOUT ``scitex-dev``.
    """
    bin_dir = tmp_path / "bin"
    if verdict_exit is None:
        bin_dir.mkdir(parents=True, exist_ok=True)
    else:
        _stub_scitex_dev(bin_dir, verdict_exit)

    env = dict(os.environ)
    # Deliberately NOT inheriting the real PATH's scitex-dev: the stub must be
    # the only one, or the test grades the installed tool instead of the stub.
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    # ...but the hook parses its payload with `${SCITEX_DEV_PYTHON:-python3}`,
    # and the PATH above only finds one if the interpreter happens to live in
    # /usr/bin or /bin. It does on an ordinary box and does NOT inside the CI
    # SIF, where every one of these tests then fell into the "could not read
    # tool_input.command" branch and asserted against the wrong path — green
    # locally, red in the release pipeline, for a reason having nothing to do
    # with the gate's logic.
    #
    # Pin the interpreter the hook already lets callers pin. This tests the
    # GATE, not the ambient location of python3.
    env["SCITEX_DEV_PYTHON"] = sys.executable

    return subprocess.run(
        ["bash", require_mergeable_verdict_sh_path()],
        input=_payload(command) if payload is None else payload,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


# --------------------------------------------------------------------------
# it ships
# --------------------------------------------------------------------------


def test_the_hook_ships_inside_the_package():
    """The whole point: an installed scitex-dev HAS this file."""
    # Arrange
    path = require_mergeable_verdict_sh_path()
    # Act
    exists = os.path.isfile(path)
    # Assert
    assert exists


def test_the_shipped_hook_starts_with_a_shebang():
    # Arrange
    path = require_mergeable_verdict_sh_path()
    # Act
    with open(path, encoding="utf-8") as handle:
        first = handle.readline()
    # Assert
    assert first.startswith("#!")


# --------------------------------------------------------------------------
# the passing direction
# --------------------------------------------------------------------------


def test_gate_allows_a_ready_pr(tmp_path):
    """The positive control: a READY verdict must not block."""
    # Arrange
    command = MERGE_CMD
    # Act
    result = _run_hook(tmp_path, command, READY)
    # Assert
    assert result.returncode == ALLOW


@pytest.mark.parametrize("command", ["git status", "gh pr list", "gh pr view 12"])
def test_gate_ignores_commands_it_does_not_own(tmp_path, command):
    """A gate that fires on unrelated commands gets disabled, and a disabled
    gate is no gate. NOT_READY is stubbed so a spurious fire would show."""
    # Arrange
    verdict = NOT_READY
    # Act
    result = _run_hook(tmp_path, command, verdict)
    # Assert
    assert result.returncode == ALLOW


# --------------------------------------------------------------------------
# the blocking direction -- proves the gate CAN fail
# --------------------------------------------------------------------------


def test_gate_blocks_a_not_ready_pr(tmp_path):
    # Arrange
    command = MERGE_CMD
    # Act
    result = _run_hook(tmp_path, command, NOT_READY)
    # Assert
    assert result.returncode == DENY


def test_gate_names_the_not_ready_verdict_when_blocking(tmp_path):
    # Arrange
    command = MERGE_CMD
    # Act
    result = _run_hook(tmp_path, command, NOT_READY)
    # Assert
    assert "NOT ready" in result.stderr


def test_gate_blocks_when_the_verdict_cannot_be_determined(tmp_path):
    """'I could not tell' is not 'yes'. Fail closed."""
    # Arrange
    command = MERGE_CMD
    # Act
    result = _run_hook(tmp_path, command, CANNOT_DETERMINE)
    # Assert
    assert result.returncode == DENY


def test_gate_distinguishes_cannot_determine_from_a_refusal(tmp_path):
    # Arrange
    command = MERGE_CMD
    # Act
    result = _run_hook(tmp_path, command, CANNOT_DETERMINE)
    # Assert
    assert "COULD NOT DETERMINE" in result.stderr


def test_gate_blocks_on_a_usage_error(tmp_path):
    """The 2026-08-09 defect: exit 2 is Click's, not a verdict."""
    # Arrange
    command = MERGE_CMD
    # Act
    result = _run_hook(tmp_path, command, USAGE)
    # Assert
    assert result.returncode == DENY


def test_gate_blames_a_stale_install_on_a_usage_error(tmp_path):
    # Arrange
    command = MERGE_CMD
    # Act
    result = _run_hook(tmp_path, command, USAGE)
    # Assert
    assert "STALE OR BROKEN" in result.stderr


def test_gate_blocks_on_an_unrecognised_exit_code(tmp_path):
    """An exit code nobody planned for must not read as permission."""
    # Arrange
    command = MERGE_CMD
    # Act
    result = _run_hook(tmp_path, command, UNRECOGNISED)
    # Assert
    assert result.returncode == DENY


def test_gate_reports_the_unrecognised_code_it_saw(tmp_path):
    # Arrange
    command = MERGE_CMD
    # Act
    result = _run_hook(tmp_path, command, UNRECOGNISED)
    # Assert
    assert str(UNRECOGNISED) in result.stderr


def test_gate_blocks_when_the_checker_is_absent(tmp_path):
    """Absence of the checker is not permission to merge."""
    # Arrange
    command = MERGE_CMD
    # Act
    result = _run_hook(tmp_path, command, None)
    # Assert
    assert result.returncode == DENY


def test_gate_says_the_checker_is_missing_from_path(tmp_path):
    # Arrange
    command = MERGE_CMD
    # Act
    result = _run_hook(tmp_path, command, None)
    # Assert
    assert "not on PATH" in result.stderr


# --------------------------------------------------------------------------
# an unreadable payload
# --------------------------------------------------------------------------


def test_unreadable_payload_does_not_block_every_tool_call(tmp_path):
    # Arrange
    junk = "not json at all"
    # Act
    result = _run_hook(tmp_path, MERGE_CMD, NOT_READY, payload=junk)
    # Assert
    assert result.returncode == ALLOW


def test_unreadable_payload_says_it_is_not_gating(tmp_path):
    """Cannot tell whether it is a merge -> do not silently claim safety."""
    # Arrange
    junk = "not json at all"
    # Act
    result = _run_hook(tmp_path, MERGE_CMD, NOT_READY, payload=junk)
    # Assert
    assert "NOT gating" in result.stderr


# EOF
