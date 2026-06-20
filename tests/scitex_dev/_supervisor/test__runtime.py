#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev._supervisor._runtime — Supervisor orchestrator.

Drives the runtime through hand-rolled seams (no real subprocess, no real
signals). The ``max_ticks`` test seam lets ``run_forever`` exit
deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scitex_dev._supervisor._child import ChildProcess
from scitex_dev._supervisor._runtime import Supervisor
from scitex_dev.jobs import JobSpec


# --------------------------------------------------------------------------- #
# Test fakes                                                                  #
# --------------------------------------------------------------------------- #


class FakePopen:
    """Minimal Popen stand-in — never exits unless caller sets returncode.

    ``pid`` is an out-of-range sentinel so ``terminate()``'s ``os.killpg``
    can never signal a real process group on the test host: the syscall
    raises ``ProcessLookupError`` (no such group), which ``terminate``
    swallows. ``wait`` is present so the SIGKILL escalation path can reap.
    """

    # Above any plausible kernel pid_max → os.killpg always ESRCHs.
    _SENTINEL_PID = 2**31 - 1

    def __init__(self, args, **_):
        self.args = args
        self._rc = None
        self.pid = self._SENTINEL_PID

    def poll(self):
        return self._rc

    def wait(self, timeout=None):
        return self._rc


class _ClockTicker:
    """Deterministic clock that advances by 1.0 per call. Test-stable."""

    def __init__(self, start: float = 100.0) -> None:
        self.t = start

    def __call__(self) -> float:
        self.t += 1.0
        return self.t


def _service_job(name="x", command="/bin/true", restart_policy="on-failure"):
    return JobSpec(
        name=name,
        kind="service",
        schedule="",
        command=command,
        description=f"test {name}",
        restart_policy=restart_policy,
    )


def _make_sup(tmp_path, *, discover, popen_factory=None):
    log_dir = tmp_path / "logs"
    state_path = tmp_path / "state.json"

    def _child_factory(job):
        return ChildProcess(
            job,
            log_dir=log_dir,
            popen_factory=popen_factory or FakePopen,
            clock=lambda: 100.0,
            sleep=lambda _s: None,  # terminate()'s grace wait never really sleeps
        )

    return Supervisor(
        discover=discover,
        log_dir=log_dir,
        state_path=state_path,
        clock=_ClockTicker(),
        sleep=lambda _s: None,  # no real sleep in tests
        child_factory=_child_factory,
    )


# --------------------------------------------------------------------------- #
# discover_service_jobs                                                        #
# --------------------------------------------------------------------------- #


def test_discover_service_jobs_filters_out_non_service(tmp_path):
    # Arrange
    mixed = [
        _service_job(name="svc"),
        JobSpec(
            name="cr",
            kind="cron",
            schedule="0 * * * *",
            command="/bin/echo",
            description="cron",
        ),
    ]
    sup = _make_sup(tmp_path, discover=lambda: mixed)
    # Act
    jobs = sup.discover_service_jobs()
    # Assert
    assert [j.name for j in jobs] == ["svc"]


# --------------------------------------------------------------------------- #
# reconcile() — start / restart / remove                                       #
# --------------------------------------------------------------------------- #


def test_reconcile_starts_added_children(tmp_path):
    # Arrange
    sup = _make_sup(tmp_path, discover=lambda: [_service_job(name="alpha")])
    # Act
    actions = sup.reconcile()
    # Assert
    assert actions == {"alpha": "added"}


def test_reconcile_drops_removed_children(tmp_path):
    # Arrange — first reconcile starts alpha; second drops it.
    state = {"jobs": [_service_job(name="alpha")]}

    def disc():
        return list(state["jobs"])

    sup = _make_sup(tmp_path, discover=disc)
    sup.reconcile()
    state["jobs"] = []  # remove
    # Act
    actions = sup.reconcile()
    # Assert
    assert actions == {"alpha": "removed"}


def test_reconcile_restarts_on_command_change(tmp_path):
    # Arrange
    state = {"jobs": [_service_job(name="alpha", command="/bin/true")]}

    def disc():
        return list(state["jobs"])

    sup = _make_sup(tmp_path, discover=disc)
    sup.reconcile()
    state["jobs"] = [_service_job(name="alpha", command="/bin/false")]
    # Act
    actions = sup.reconcile()
    # Assert
    assert actions == {"alpha": "restarted"}


def test_reconcile_unchanged_for_identical_jobs(tmp_path):
    # Arrange
    job = _service_job(name="alpha")
    sup = _make_sup(tmp_path, discover=lambda: [job])
    sup.reconcile()
    # Act
    actions = sup.reconcile()
    # Assert
    assert actions == {"alpha": "unchanged"}


# --------------------------------------------------------------------------- #
# tick() — poll + restart + state write                                       #
# --------------------------------------------------------------------------- #


def test_tick_writes_state_file(tmp_path):
    # Arrange
    sup = _make_sup(tmp_path, discover=lambda: [_service_job(name="alpha")])
    sup.start_all()
    # Act
    sup.tick()
    # Assert
    assert (tmp_path / "state.json").exists()


def test_tick_state_file_contains_alpha(tmp_path):
    # Arrange
    sup = _make_sup(tmp_path, discover=lambda: [_service_job(name="alpha")])
    sup.start_all()
    sup.tick()
    # Act
    data = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    # Assert
    names = [c["name"] for c in data["children"]]
    assert "alpha" in names


def test_tick_restarts_a_failed_on_failure_child(tmp_path):
    # Arrange — start, exit non-zero, tick → expect restart.
    sup = _make_sup(
        tmp_path,
        discover=lambda: [_service_job(name="alpha", restart_policy="on-failure")],
    )
    sup.start_all()
    # Drive the exit through the proc handle (non-zero → on-failure restart).
    sup.children["alpha"]._proc._rc = 1  # type: ignore[union-attr]
    # Act
    sup.tick()
    # Assert — should be running again with a fresh Popen.
    assert sup.children["alpha"].restart_count == 1


# --------------------------------------------------------------------------- #
# run_forever — bounded by max_ticks                                          #
# --------------------------------------------------------------------------- #


def test_run_forever_bounded_by_max_ticks(tmp_path):
    # Arrange
    sup = _make_sup(tmp_path, discover=lambda: [_service_job(name="alpha")])
    # Act
    rc = sup.run_forever(install_signal_handlers=False, max_ticks=2)
    # Assert
    assert rc == 0


def test_run_forever_writes_final_state_on_shutdown(tmp_path):
    # Arrange
    sup = _make_sup(tmp_path, discover=lambda: [_service_job(name="alpha")])
    # Act
    sup.run_forever(install_signal_handlers=False, max_ticks=1)
    # Assert
    assert (tmp_path / "state.json").exists()


# --------------------------------------------------------------------------- #
# Signal-driven flags                                                          #
# --------------------------------------------------------------------------- #


def test_request_reload_sets_flag(tmp_path):
    # Arrange
    sup = _make_sup(tmp_path, discover=lambda: [])
    # Act
    sup.request_reload()
    # Assert
    assert sup._reload_requested is True


def test_request_shutdown_sets_flag(tmp_path):
    # Arrange
    sup = _make_sup(tmp_path, discover=lambda: [])
    # Act
    sup.request_shutdown()
    # Assert
    assert sup._shutdown_requested is True


def test_run_forever_exits_when_shutdown_requested_before_first_tick(tmp_path):
    # Arrange
    sup = _make_sup(tmp_path, discover=lambda: [])
    sup.request_shutdown()
    # Act
    rc = sup.run_forever(install_signal_handlers=False, max_ticks=10_000)
    # Assert
    assert rc == 0


# EOF
