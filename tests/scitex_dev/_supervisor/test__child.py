#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev._supervisor._child — per-child state machine.

Real fakes only — the ``popen_factory`` + ``clock`` seams let us drive
the state machine deterministically without spawning real processes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._supervisor._child import (
    DEFAULT_CIRCUIT_FAILURE_LIMIT,
    ChildProcess,
    _RestartLedger,
)
from scitex_dev.jobs import JobSpec


# --------------------------------------------------------------------------- #
# Test fakes                                                                  #
# --------------------------------------------------------------------------- #


class FakePopen:
    """Stand-in for subprocess.Popen with a hand-driven exit code."""

    def __init__(self, args, **_):
        self.args = args
        self._rc: int | None = None  # None = still running
        # Realistic-ish PID so killpg paths see something.
        self.pid = 99999

    def set_exit(self, rc: int) -> None:
        self._rc = rc

    def poll(self):
        return self._rc

    def wait(self, timeout=None):  # pragma: no cover — tests don't wait
        return self._rc or 0


def _service_job(name="x", command="/bin/true", restart_policy="on-failure"):
    return JobSpec(
        name=name,
        kind="service",
        schedule="",
        command=command,
        description=f"test job {name}",
        restart_policy=restart_policy,
    )


def _make_child(
    *,
    log_dir,
    job=None,
    popen_factory=None,
    clock=None,
    circuit_failure_limit=DEFAULT_CIRCUIT_FAILURE_LIMIT,
    circuit_window_sec=60.0,
):
    return ChildProcess(
        job or _service_job(),
        log_dir=log_dir,
        popen_factory=popen_factory or FakePopen,
        clock=clock or (lambda: 0.0),
        circuit_failure_limit=circuit_failure_limit,
        circuit_window_sec=circuit_window_sec,
    )


# --------------------------------------------------------------------------- #
# Construction                                                                 #
# --------------------------------------------------------------------------- #


def test_child_rejects_non_service_kind(tmp_path):
    # Arrange
    timer = JobSpec(
        name="t",
        kind="timer",
        schedule="0 * * * *",
        command="/bin/true",
        description="timer",
        on_unit_active_sec="1h",
    )
    # Act
    # Assert
    with pytest.raises(ValueError):
        ChildProcess(timer, log_dir=tmp_path)


def test_child_initial_status_is_stopped(tmp_path):
    # Arrange
    # Act
    c = _make_child(log_dir=tmp_path)
    # Assert
    assert c.status == "stopped"


def test_child_initial_pid_is_none(tmp_path):
    # Arrange
    # Act
    c = _make_child(log_dir=tmp_path)
    # Assert
    assert c.pid is None


# --------------------------------------------------------------------------- #
# start()                                                                      #
# --------------------------------------------------------------------------- #


def test_child_start_creates_log_dir(tmp_path):
    # Arrange
    log_dir = tmp_path / "logs"
    c = _make_child(log_dir=log_dir)
    # Act
    c.start()
    # Assert
    assert log_dir.is_dir()


def test_child_start_transitions_status_to_running(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path)
    # Act
    c.start()
    # Assert
    assert c.status == "running"


def test_child_start_records_argv(tmp_path):
    # Arrange
    job = _service_job(command="/bin/true --flag value")
    c = _make_child(log_dir=tmp_path, job=job)
    # Act
    c.start()
    # Assert — argv carries the resolved command (head absolutised).
    assert c.argv[0] == "/bin/true"


def test_child_start_idempotent_while_running(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path)
    c.start()
    first_pid = c.pid
    # Act
    c.start()
    # Assert
    assert c.pid == first_pid


def test_child_start_records_popen_failure_against_breaker(tmp_path):
    # Arrange
    def boom_factory(*_a, **_kw):
        raise FileNotFoundError("no such binary")

    c = _make_child(log_dir=tmp_path, popen_factory=boom_factory)
    # Act
    c.start()
    # Assert — one failure recorded; breaker not yet open (limit > 1).
    assert c.status == "stopped"


# --------------------------------------------------------------------------- #
# poll() + restart policy                                                      #
# --------------------------------------------------------------------------- #


def test_poll_returns_running_for_live_child(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path)
    c.start()
    # Act
    s = c.poll()
    # Assert
    assert s == "running"


def test_poll_transitions_to_stopped_on_clean_exit(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path)
    c.start()
    c._proc.set_exit(0)  # type: ignore[union-attr]
    # Act
    c.poll()
    # Assert
    assert c.status == "stopped"


def test_poll_captures_last_exit_code(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path)
    c.start()
    c._proc.set_exit(7)  # type: ignore[union-attr]
    # Act
    c.poll()
    # Assert
    assert c.last_exit_code == 7


def test_should_restart_true_for_failed_exit_under_on_failure(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path, job=_service_job(restart_policy="on-failure"))
    c.start()
    c._proc.set_exit(1)  # type: ignore[union-attr]
    c.poll()
    # Act
    # Assert
    assert c.should_restart() is True


def test_should_restart_false_for_clean_exit_under_on_failure(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path, job=_service_job(restart_policy="on-failure"))
    c.start()
    c._proc.set_exit(0)  # type: ignore[union-attr]
    c.poll()
    # Act
    restart = c.should_restart()
    # Assert
    assert restart is False


def test_should_restart_true_under_always_even_on_clean_exit(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path, job=_service_job(restart_policy="always"))
    c.start()
    c._proc.set_exit(0)  # type: ignore[union-attr]
    c.poll()
    # Act
    restart = c.should_restart()
    # Assert
    assert restart is True


def test_should_restart_false_under_no_policy(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path, job=_service_job(restart_policy="no"))
    c.start()
    c._proc.set_exit(0)  # type: ignore[union-attr]
    c.poll()
    # Act
    restart = c.should_restart()
    # Assert
    assert restart is False


def test_should_restart_initial_first_start_for_on_failure(tmp_path):
    # Arrange — never started; restart_policy says yes to first bring-up.
    c = _make_child(log_dir=tmp_path, job=_service_job(restart_policy="on-failure"))
    # Act
    restart = c.should_restart()
    # Assert
    assert restart is True


# --------------------------------------------------------------------------- #
# Circuit breaker                                                              #
# --------------------------------------------------------------------------- #


def test_breaker_trips_after_failure_limit(tmp_path):
    # Arrange — low limit so we don't have to loop 5 times.
    c = _make_child(log_dir=tmp_path, circuit_failure_limit=2)
    for _ in range(2):
        c.start()
        c._proc.set_exit(1)  # type: ignore[union-attr]
        c.poll()
    # Act
    tripped = c.circuit_open
    # Assert
    assert tripped is True


def test_breaker_blocks_start_when_open(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path, circuit_failure_limit=1)
    c.start()
    c._proc.set_exit(2)  # type: ignore[union-attr]
    c.poll()  # records failure → breaker opens (limit=1)
    # Act
    c.start()
    # Assert — start was a no-op; status is failed, no Popen handle.
    assert c.status == "failed" and c.pid is None


def test_breaker_reset_re_arms(tmp_path):
    # Arrange — open the breaker first (limit=1 → one failure trips it;
    # the breaker-opens behaviour itself is covered by
    # test_breaker_trips_after_failure_limit).
    c = _make_child(log_dir=tmp_path, circuit_failure_limit=1)
    c.start()
    c._proc.set_exit(1)  # type: ignore[union-attr]
    c.poll()
    # Act
    c.reset_breaker()
    # Assert
    assert c.circuit_open is False


def test_ledger_window_drops_old_failures():
    # Arrange — explicit clock so the window calculation is deterministic.
    led = _RestartLedger(failure_limit=3, window_sec=10.0)
    led.record_failure(now=0.0)
    led.record_failure(now=1.0)
    led.record_failure(now=100.0)  # ← old entries fall out of window first
    # Act
    still_open = led.circuit_open
    # Assert — only one entry remains in the window → breaker closed.
    assert still_open is False


# --------------------------------------------------------------------------- #
# snapshot()                                                                   #
# --------------------------------------------------------------------------- #


def test_snapshot_includes_name(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path, job=_service_job(name="alpha"))
    # Act
    snap = c.snapshot()
    # Assert
    assert snap["name"] == "alpha"


def test_snapshot_includes_log_path(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path, job=_service_job(name="alpha"))
    # Act
    snap = c.snapshot()
    # Assert
    assert snap["log_path"] == str(Path(tmp_path) / "alpha.log")


def test_snapshot_reflects_running_status_after_start(tmp_path):
    # Arrange
    c = _make_child(log_dir=tmp_path)
    c.start()
    # Act
    snap = c.snapshot()
    # Assert
    assert snap["status"] == "running"


# EOF
