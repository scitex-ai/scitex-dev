#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for ``scitex-dev ecosystem up`` (post-2026-06-14 redesign).

The legacy per-leaf systemd-unit + master-reconcile shape is gone; this
test file covers the new shape: ONE collective supervisor unit gets
written, cron-native + lowered-timer entries go to the managed crontab
block. Real fakes only (PA-306 / STX-NM); ``run_up`` exposes
``discover``, ``systemctl_runner``, ``unit_dir`` + ``echo`` as kwarg
seams so tests substitute hand-rolled callables.
"""

from __future__ import annotations

import subprocess

from scitex_dev._cli.ecosystem._cmds import _up
from scitex_dev._cli.ecosystem._cmds._up_supervisor_unit import (
    SUPERVISOR_UNIT_NAME,
)
from scitex_dev.jobs import JobSpec


def _completed(
    rc: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=rc, stdout=stdout, stderr=stderr
    )


def _ok_systemctl(args, **_):
    return _completed(rc=0)


def _service_provider():
    return [
        JobSpec(
            name="mock.dashboard",
            kind="service",
            schedule="",
            command="mock-dashboard serve --port 9999",
            description="mock long-running dashboard",
            on_boot_sec="5s",
            restart_policy="on-failure",
        )
    ]


def _timer_provider():
    return [
        JobSpec(
            name="mock.refresh",
            kind="timer",
            schedule="*/15 * * * *",
            command="mock refresh",
            description="mock periodic refresh",
            on_unit_active_sec="15min",
        )
    ]


def _cron_provider():
    return [
        JobSpec(
            name="mock.cron",
            kind="cron",
            schedule="0 * * * *",
            command="mock-cron run",
            description="mock cron",
        )
    ]


def _degraded_timer_provider():
    """Two timers cron cannot honour — each pins a leaf-owned `venv`.

    NOT `timeout_sec`: since 2026-08-19 the lowering CARRIES that as a
    `timeout <N> ` prefix, so it is no longer a refusal trigger for an
    ordinary command. `venv` still is — a crontab line cannot select an
    interpreter. Without ``--allow-lossy-timer-lowering`` each of these
    is REFUSED INDIVIDUALLY (the block still installs everything else),
    which is the path the tests below interrogate.
    """
    return [
        JobSpec(
            name="mock.bounded-a",
            kind="timer",
            schedule="*/15 * * * *",
            command="mock refresh-a",
            description="mock refresh a",
            on_unit_active_sec="15min",
            venv="/opt/leaf-a",
        ),
        JobSpec(
            name="mock.bounded-b",
            kind="timer",
            schedule="*/30 * * * *",
            command="mock refresh-b",
            description="mock refresh b",
            on_unit_active_sec="30min",
            venv="/opt/leaf-b",
        ),
    ]


# --------------------------------------------------------------------------- #
# UpResult defaults                                                            #
# --------------------------------------------------------------------------- #


def test_upresult_default_supervisor_unit_written_is_false():
    # Arrange
    # Act
    result = _up.UpResult()
    # Assert
    assert result.supervisor_unit_written is False


def test_upresult_default_supervisor_unit_enabled_is_false():
    # Arrange
    # Act
    result = _up.UpResult()
    # Assert
    assert result.supervisor_unit_enabled is False


# --------------------------------------------------------------------------- #
# run_up — supervisor unit always written                                      #
# --------------------------------------------------------------------------- #


def test_run_up_writes_supervisor_unit_to_unit_dir(tmp_path):
    # Arrange
    # Act
    _up.run_up(
        yes=False,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
        discover=lambda: [],
    )
    # Assert
    assert (tmp_path / SUPERVISOR_UNIT_NAME).exists()


def test_run_up_supervisor_unit_written_flag_true_even_without_yes(tmp_path):
    # Arrange
    # Act
    result = _up.run_up(
        yes=False,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
        discover=lambda: [],
    )
    # Assert — writing the unit file has no side effects worth gating.
    assert result.supervisor_unit_written is True


# --- a cron refusal must not keep the daemon down -------------------------
#
# REGRESSION. `TimerLoweringError` used to return before the supervisor was
# written or enabled, so nine cron-bound jobs in ONE package kept the whole
# fleet's supervisor from ever coming up — measured 2026-08-18: zero
# scitex-dev timers on any host. The crontab and the supervisor unit are
# independent artifacts; refusing the first is not a reason to refuse the
# second.


def _degrading_timer():
    """A timer pinning a venv cron cannot select — forces the refusal."""
    return JobSpec(
        name="pkg.refresh-thing",
        kind="timer",
        schedule="",
        command="true",
        description="d",
        on_unit_active_sec="5min",
        venv="/opt/leaf-c",
    )


def test_up_writes_the_supervisor_unit(tmp_path):
    # Arrange
    job = _degrading_timer()
    # Act
    _up.run_up(
        yes=False,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
        discover=lambda: [job],
    )
    # Assert — the unit file exists despite the cron half refusing.
    assert (tmp_path / SUPERVISOR_UNIT_NAME).exists()


def test_up_result_says_the_unit_was_written(tmp_path):
    """The report must match what happened, not return a stale default."""
    # Arrange
    job = _degrading_timer()
    # Act
    result = _up.run_up(
        yes=False,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
        discover=lambda: [job],
    )
    # Assert
    assert result.supervisor_unit_written is True


def test_run_up_does_not_enable_without_yes(tmp_path):
    # Arrange
    calls: list[list[str]] = []

    def runner(args, **_):
        calls.append(list(args))
        return _completed(rc=0)

    # Act
    _up.run_up(
        yes=False,
        systemctl_runner=runner,
        unit_dir=tmp_path,
        echo=lambda _: None,
        discover=lambda: [],
    )
    # Assert
    assert calls == []


def test_run_up_yes_calls_enable_now_on_supervisor_unit(tmp_path):
    # Arrange
    calls: list[list[str]] = []

    def runner(args, **_):
        calls.append(list(args))
        return _completed(rc=0)

    # Act
    _up.run_up(
        yes=True,
        systemctl_runner=runner,
        unit_dir=tmp_path,
        echo=lambda _: None,
        discover=lambda: [],
    )
    # Assert
    assert ["enable", "--now", SUPERVISOR_UNIT_NAME] in calls


# --------------------------------------------------------------------------- #
# run_up — timer-kind lowered to cron                                          #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# run_up — the ABORT path must carry OUT the count that caused it              #
#                                                                              #
# `degraded_n` is computed before the lowering is attempted, and the refusal    #
# branch used to discard it: `return UpResult(error=str(exc))`. Every other     #
# field then took its default, so a programmatic caller reading                #
# `result.timer_jobs_degraded` on a refusal saw 0 — "no jobs degraded" —        #
# about the one run that refused to install ANYTHING precisely because jobs     #
# were degraded. Zero-subjects and zero-problems rendered identically on the    #
# single path where they mean opposite things, and a before/after comparison    #
# taken from that field would have reported "0 degraded" for a run that         #
# installed nothing. Reported by scitex-agent-container, 2026-08-17, while      #
# measuring 9 -> 0 through this orchestrator rather than by reading the code.   #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# run_up — service-kind does NOT produce per-leaf files                       #
# --------------------------------------------------------------------------- #


def test_run_up_does_not_write_per_leaf_service_file_for_service_kind(tmp_path):
    # Arrange
    # Act
    _up.run_up(
        yes=False,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
        discover=_service_provider,
    )
    # Assert — the legacy `<name>.service` per-leaf write is gone.
    assert not (tmp_path / "mock.dashboard.service").exists()


def test_run_up_does_not_write_per_leaf_timer_file_for_timer_kind(tmp_path):
    # Arrange
    # Act
    _up.run_up(
        yes=False,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
        discover=_timer_provider,
    )
    # Assert — the legacy `<name>.timer` per-leaf write is gone.
    assert not (tmp_path / "mock.refresh.timer").exists()


def test_run_up_does_not_write_master_reconcile_unit(tmp_path):
    # Arrange
    # Act
    _up.run_up(
        yes=False,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
        discover=_service_provider,
    )
    # Assert — the master reconcile unit is gone in the new design.
    assert not (tmp_path / "scitex-dev-ecosystem-reconcile.service").exists()


# --------------------------------------------------------------------------- #
# run_up — systemctl missing                                                   #
# --------------------------------------------------------------------------- #


def test_run_up_reports_systemctl_missing_when_no_binary(tmp_path):
    # Arrange — real fake for the executable-lookup seam: `systemctl` absent.
    absent_which = lambda _name: None
    # Act
    result = _up.run_up(
        yes=False,
        systemctl_runner=_ok_systemctl,
        unit_dir=tmp_path,
        echo=lambda _: None,
        discover=lambda: [],
        which=absent_which,
    )
    # Assert
    assert result.systemctl_missing is True


# --------------------------------------------------------------------------- #
# _systemctl seam                                                              #
# --------------------------------------------------------------------------- #


def test_systemctl_returns_true_on_rc0():
    # Arrange
    # Act
    ok = _up._systemctl(["daemon-reload"], runner=_ok_systemctl, echo=lambda _: None)
    # Assert
    assert ok is True


def test_systemctl_returns_false_on_non_zero_rc():
    # Arrange
    def runner(args, **_):
        return _completed(rc=1, stderr="boom")

    # Act
    ok = _up._systemctl(["enable", "x.service"], runner=runner, echo=lambda _: None)
    # Assert
    assert ok is False


def test_systemctl_returns_false_when_binary_missing():
    # Arrange
    def runner(args, **_):
        raise FileNotFoundError("systemctl")

    # Act
    ok = _up._systemctl(["daemon-reload"], runner=runner, echo=lambda _: None)
    # Assert
    assert ok is False


# EOF
