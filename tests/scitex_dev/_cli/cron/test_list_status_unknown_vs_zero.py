"""`cron list` / `cron status` must not report "could not look" as zero.

Regression tests for the near-miss that motivated them: a peer agent ran
`scitex-dev cron list` inside a container with no `crontab` binary, read
`installed (0): (none)` as "13 automations registered, NONE running", and
nearly escalated a fleet-wide automation outage. The jobs were in fact
running on the host.

Three states must stay distinct:

  * crontab read, managed lines found   -> the count
  * crontab read, genuinely empty       -> zero  (the CONTROL arm below:
                                           it proves the fix did not just
                                           relabel everything UNKNOWN)
  * crontab NOT readable                -> UNKNOWN, never zero

Per the no-mocks rule (PA-306 / STX-NM*) nothing here is mocked or
monkeypatched: the unit tests inject a real callable through the existing
`runner=` seam, and the CLI tests put a REAL executable (or nothing at
all) on a real PATH and run the real command.
"""

from __future__ import annotations

import json
import os
import stat

import click
from click.testing import CliRunner

from scitex_dev._cli.cron import _crontab
from scitex_dev._cli.cron._cmd import register_cron_commands


# ---------------------------------------------------------------------------
# helpers — real processes and real PATHs, no mocks
# ---------------------------------------------------------------------------


def _cron_cli() -> click.Group:
    """Build the real `cron` group on a throwaway parent."""

    @click.group()
    def main() -> None:
        pass

    register_cron_commands(main)
    return main


def _bin_dir_with_crontab(tmp_path, script: str):
    """Create a directory holding a REAL executable named `crontab`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    exe = bin_dir / "crontab"
    exe.write_text(script)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _empty_crontab_bin(tmp_path):
    """A crontab that reads successfully and is genuinely EMPTY."""
    return _bin_dir_with_crontab(tmp_path, "#!/bin/sh\nexit 0\n")


def _no_crontab_path_env() -> dict:
    """An env whose PATH contains no `crontab` binary at all."""
    return {"PATH": "/nonexistent-bin-dir-for-tests"}


def _invoke(args, env):
    return CliRunner().invoke(_cron_cli(), args, env=env)


# ---------------------------------------------------------------------------
# read_crontab_state — the three states at the source
# ---------------------------------------------------------------------------


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_read_state_reports_not_readable_when_binary_is_missing():
    # Arrange
    def missing_binary(*args, **kwargs):
        raise FileNotFoundError("crontab")

    # Act
    state = _crontab.read_crontab_state(runner=missing_binary)
    # Assert
    assert state.readable is False


def test_read_state_names_the_missing_binary_as_the_reason():
    # Arrange
    def missing_binary(*args, **kwargs):
        raise FileNotFoundError("crontab")

    # Act
    state = _crontab.read_crontab_state(runner=missing_binary)
    # Assert
    assert "crontab" in (state.reason or "") and "PATH" in (state.reason or "")


def test_read_state_reports_readable_when_user_simply_has_no_crontab():
    # Arrange — `crontab -l` exits 1 with this message for an empty crontab.
    def fake_runner(*args, **kwargs):
        return _FakeCompletedProcess(returncode=1, stderr="no crontab for x")

    # Act
    state = _crontab.read_crontab_state(runner=fake_runner)
    # Assert — READ, and genuinely empty: not the unknown state.
    assert state.readable is True and state.text == ""


def test_read_state_reports_not_readable_on_an_unexplained_nonzero_exit():
    # Arrange
    def fake_runner(*args, **kwargs):
        return _FakeCompletedProcess(returncode=1, stderr="must be privileged")

    # Act
    state = _crontab.read_crontab_state(runner=fake_runner)
    # Assert
    assert state.readable is False


def test_read_state_returns_the_crontab_text_when_the_read_succeeds():
    # Arrange
    def fake_runner(*args, **kwargs):
        return _FakeCompletedProcess(returncode=0, stdout="# my cron\n")

    # Act
    state = _crontab.read_crontab_state(runner=fake_runner)
    # Assert
    assert state.readable is True and state.text == "# my cron\n"


# ---------------------------------------------------------------------------
# cron list — human output
# ---------------------------------------------------------------------------


def test_list_human_output_says_unknown_when_crontab_is_absent():
    # Arrange
    env = _no_crontab_path_env()
    # Act
    result = _invoke(["cron", "list"], env)
    # Assert
    assert "installed: UNKNOWN" in result.output


def test_list_human_output_does_not_claim_zero_installed_when_crontab_is_absent():
    # Arrange
    env = _no_crontab_path_env()
    # Act
    result = _invoke(["cron", "list"], env)
    # Assert — the exact string that caused the near-miss must be gone.
    assert "installed (0)" not in result.output


def test_list_human_output_still_reports_zero_when_crontab_is_readable_and_empty(
    tmp_path,
):
    # Arrange — CONTROL: a real crontab binary, real successful read, empty.
    env = {"PATH": f"{_empty_crontab_bin(tmp_path)}{os.pathsep}/usr/bin"}
    # Act
    result = _invoke(["cron", "list"], env)
    # Assert — this arm must NOT have been relabelled UNKNOWN.
    assert "installed (0)" in result.output and "UNKNOWN" not in result.output


# ---------------------------------------------------------------------------
# cron list — --json
# ---------------------------------------------------------------------------


def test_list_json_marks_installed_state_unknown_when_crontab_is_absent():
    # Arrange
    env = _no_crontab_path_env()
    # Act
    payload = json.loads(_invoke(["cron", "list", "--json"], env).output)
    # Assert
    assert payload["installed_state"] == "unknown"


def test_list_json_installed_is_null_not_empty_list_when_crontab_is_absent():
    # Arrange
    env = _no_crontab_path_env()
    # Act
    payload = json.loads(_invoke(["cron", "list", "--json"], env).output)
    # Assert — a consumer calling len() must not silently read zero.
    assert payload["installed"] is None


def test_list_json_carries_a_reason_when_crontab_is_absent():
    # Arrange
    env = _no_crontab_path_env()
    # Act
    payload = json.loads(_invoke(["cron", "list", "--json"], env).output)
    # Assert
    assert payload["installed_unavailable_reason"]


def test_list_json_reports_state_read_and_empty_list_when_crontab_is_empty(
    tmp_path,
):
    # Arrange — CONTROL arm.
    env = {"PATH": f"{_empty_crontab_bin(tmp_path)}{os.pathsep}/usr/bin"}
    # Act
    payload = json.loads(_invoke(["cron", "list", "--json"], env).output)
    # Assert
    assert payload["installed_state"] == "read" and payload["installed"] == []


# ---------------------------------------------------------------------------
# cron status — same read path, same collapse
# ---------------------------------------------------------------------------


def test_status_human_output_says_unknown_when_crontab_is_absent():
    # Arrange
    env = _no_crontab_path_env()
    # Act
    result = _invoke(["cron", "status"], env)
    # Assert
    assert "crontab: UNKNOWN" in result.output


def test_status_json_marks_crontab_state_unknown_when_crontab_is_absent():
    # Arrange
    env = _no_crontab_path_env()
    # Act
    payload = json.loads(_invoke(["cron", "status", "--json"], env).output)
    # Assert
    assert payload["crontab_state"] == "unknown"


def test_status_json_marks_each_job_unknown_not_no_when_crontab_is_absent():
    # Arrange
    env = _no_crontab_path_env()
    # Act
    payload = json.loads(_invoke(["cron", "status", "--json"], env).output)
    # Assert — "no" would be a claim we cannot make from here.
    assert {r["installed"] for r in payload["jobs"]} == {"unknown"}


def test_status_json_reports_state_read_when_crontab_is_readable_and_empty(
    tmp_path,
):
    # Arrange — CONTROL arm.
    env = {"PATH": f"{_empty_crontab_bin(tmp_path)}{os.pathsep}/usr/bin"}
    # Act
    payload = json.loads(_invoke(["cron", "status", "--json"], env).output)
    # Assert
    assert payload["crontab_state"] == "read"


def test_status_json_reports_each_job_not_installed_when_crontab_is_empty(
    tmp_path,
):
    # Arrange — CONTROL arm: an empty crontab genuinely installs nothing.
    env = {"PATH": f"{_empty_crontab_bin(tmp_path)}{os.pathsep}/usr/bin"}
    # Act
    payload = json.loads(_invoke(["cron", "status", "--json"], env).output)
    # Assert — this arm must NOT have been relabelled UNKNOWN.
    assert {r["installed"] for r in payload["jobs"]} == {"no"}


# EOF
