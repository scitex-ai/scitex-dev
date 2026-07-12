#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev.gui_runtime._runtime — GuiRuntime + pid_alive.

Real fakes only (STX-NM policy: no `unittest.mock`, no `monkeypatch`).
Liveness edge cases (process gone, zombie, wrong owner) are exercised
against real subprocesses; the one branch a test process cannot
portably manufacture for real — a signal-permission denial from the
kernel (no spare uid to target) — is exercised via `pid_alive`'s
injectable `kill` seam with a real hand-rolled fake function, per the
NM001 replacement menu ("restructure so the collaborator is injected
as an argument").
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scitex_dev.gui_runtime import GuiRuntime, pid_alive


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "gui.json"


@pytest.fixture
def zombie_pid():
    """Yield the pid of a real zombie process, then reap it on teardown.

    A child that has exited but whose parent hasn't called `wait()`
    yet stays a zombie — it still answers `os.kill(pid, 0)` but is
    already dead. The loop below polls `/proc/<pid>/stat` (never
    calling `Popen.wait`/`poll`, both of which would reap it) until
    the kernel marks it `Z`.
    """
    if not Path("/proc").is_dir():
        pytest.skip("zombie detection requires /proc (Linux only)")
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    stat_path = Path(f"/proc/{child.pid}/stat")
    deadline = time.monotonic() + 5.0
    state = ""
    while time.monotonic() < deadline:
        try:
            state = stat_path.read_text().rpartition(")")[2].split()[0]
        except OSError:
            state = ""
        if state == "Z":
            break
        time.sleep(0.02)
    yield child.pid
    child.wait(timeout=5)


def _deny_signal(pid, sig):
    """Real hand-rolled fake `os.kill` — always raises PermissionError."""
    raise PermissionError(f"pid {pid} owned by another user")


# --------------------------------------------------------------------------- #
# pid_alive                                                                    #
# --------------------------------------------------------------------------- #


def test_pid_alive_returns_true_for_the_current_process():
    # Arrange
    pid = os.getpid()
    # Act
    alive = pid_alive(pid)
    # Assert
    assert alive


def test_pid_alive_returns_false_for_non_positive_pid():
    # Arrange
    pid = -1
    # Act
    alive = pid_alive(pid)
    # Assert
    assert not alive


def test_pid_alive_returns_false_for_a_reaped_child_process():
    # Arrange
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=5)
    # Act
    alive = pid_alive(child.pid)
    # Assert
    assert not alive


def test_pid_alive_returns_false_for_a_zombie_child_process(zombie_pid):
    # Arrange
    # (zombie_pid fixture already produced a real zombied child)
    # Act
    alive = pid_alive(zombie_pid)
    # Assert
    assert not alive


def test_pid_alive_returns_true_when_signal_raises_permission_error():
    # Arrange
    # (_deny_signal is a real function standing in for a wrong-owner pid)
    # Act
    alive = pid_alive(4242, kill=_deny_signal)
    # Assert
    assert alive


# --------------------------------------------------------------------------- #
# GuiRuntime.read_state / write_state / clear_state                           #
# --------------------------------------------------------------------------- #


def test_read_state_returns_none_for_a_missing_state_file(state_file):
    # Arrange
    runtime = GuiRuntime(state_file)
    # Act
    result = runtime.read_state()
    # Assert
    assert result is None


def test_read_state_returns_none_for_malformed_json(state_file):
    # Arrange
    state_file.write_text("{not json")
    runtime = GuiRuntime(state_file)
    # Act
    result = runtime.read_state()
    # Assert
    assert result is None


def test_read_state_returns_none_for_valid_json_that_is_not_an_object(state_file):
    # Arrange
    state_file.write_text("[1, 2, 3]")
    runtime = GuiRuntime(state_file)
    # Act
    result = runtime.read_state()
    # Assert
    assert result is None


def test_write_state_round_trips_the_base_fields(state_file):
    # Arrange
    runtime = GuiRuntime(state_file)
    runtime.write_state(123, 5050, "127.0.0.1")
    # Act
    state = runtime.read_state()
    # Assert
    assert (state["pid"], state["port"], state["host"]) == (123, 5050, "127.0.0.1")


def test_write_state_round_trips_package_specific_extra_fields(state_file):
    # Arrange
    runtime = GuiRuntime(state_file)
    runtime.write_state(123, 5050, "127.0.0.1", project="/proj", board="main")
    # Act
    state = runtime.read_state()
    # Assert
    assert (state["project"], state["board"]) == ("/proj", "main")


def test_write_state_records_a_started_at_timestamp(state_file):
    # Arrange
    runtime = GuiRuntime(state_file)
    runtime.write_state(123, 5050, "127.0.0.1")
    # Act
    state = runtime.read_state()
    # Assert
    assert state["started_at"]


def test_write_state_creates_missing_parent_directories(state_file):
    # Arrange
    nested = state_file.parent / "nested" / "deeper" / "gui.json"
    runtime = GuiRuntime(nested)
    # Act
    runtime.write_state(123, 5050, "127.0.0.1")
    # Assert
    assert nested.is_file()


def test_clear_state_removes_an_existing_state_file(state_file):
    # Arrange
    runtime = GuiRuntime(state_file)
    runtime.write_state(123, 5050, "127.0.0.1")
    # Act
    runtime.clear_state()
    # Assert
    assert not state_file.exists()


def test_clear_state_is_idempotent_when_already_missing(state_file):
    # Arrange
    runtime = GuiRuntime(state_file)
    # Act
    runtime.clear_state()
    # Assert
    assert not state_file.exists()


def test_path_property_returns_the_constructor_argument(state_file):
    # Arrange
    runtime = GuiRuntime(state_file)
    # Act
    got = runtime.path
    # Assert
    assert got == state_file


# --------------------------------------------------------------------------- #
# GuiRuntime.status                                                            #
# --------------------------------------------------------------------------- #


def test_status_reports_not_running_when_state_is_missing(state_file):
    # Arrange
    runtime = GuiRuntime(state_file)
    # Act
    result = runtime.status()
    # Assert
    assert result == {"running": False}


def test_status_reports_running_with_url_for_a_live_pid(state_file):
    # Arrange
    runtime = GuiRuntime(state_file)
    runtime.write_state(os.getpid(), 5050, "127.0.0.1")
    # Act
    result = runtime.status()
    # Assert
    assert result["url"] == "http://127.0.0.1:5050"


def test_status_self_heals_stale_state_for_a_dead_pid(state_file):
    # Arrange
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=5)
    runtime = GuiRuntime(state_file)
    runtime.write_state(child.pid, 5050, "127.0.0.1")
    # Act
    result = runtime.status()
    # Assert
    assert result["stale_state_cleared"] and not state_file.exists()


def test_status_self_heals_state_with_a_non_integer_pid(state_file):
    # Arrange
    state_file.write_text('{"pid": "not-a-pid", "port": 5050, "host": "x"}')
    runtime = GuiRuntime(state_file)
    # Act
    result = runtime.status()
    # Assert
    assert result["stale_state_cleared"] and not state_file.exists()


# --------------------------------------------------------------------------- #
# GuiRuntime.stop                                                             #
# --------------------------------------------------------------------------- #


def test_stop_is_idempotent_when_nothing_is_running(state_file):
    # Arrange
    runtime = GuiRuntime(state_file)
    # Act
    result = runtime.stop()
    # Assert
    assert result == {"stopped": False, "running": False}


def test_stop_terminates_the_recorded_process(state_file):
    # Arrange
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    runtime = GuiRuntime(state_file)
    runtime.write_state(child.pid, 5050, "127.0.0.1")
    # Act
    result = runtime.stop(timeout=5.0)
    child.wait(timeout=5)
    # Assert
    assert result["stopped"] and result["terminated"]


def test_stop_clears_the_state_file_after_stopping(state_file):
    # Arrange
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    runtime = GuiRuntime(state_file)
    runtime.write_state(child.pid, 5050, "127.0.0.1")
    # Act
    runtime.stop(timeout=5.0)
    child.wait(timeout=5)
    # Assert
    assert not state_file.exists()


# EOF
