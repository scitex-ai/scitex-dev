#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for ``ensure_service`` backend selection + install paths.

No real ``systemctl`` is invoked and no real background process is
spawned: the availability probe, the command runner, and the detached
launcher are all injected as callables. A real ``scitex_dev.jobs``
entry-point provider (the ``installed_job_provider`` conftest fixture)
supplies the ``kind='service'`` JobSpec so discovery runs through the
production ``importlib.metadata`` path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev.jobs import JobSpec
from scitex_dev.jobs import _ensure


class _Recorder:
    """Injected run_fn that records argv and returns a rc=0 result."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, argv):
        self.calls.append(list(argv))

        class _R:
            returncode = 0
            stdout = "running\n"

        return _R()


def _svc_provider():
    return [
        JobSpec(
            name="sac.listen",
            kind="service",
            schedule="",
            command="sac listen --port 7878",
            description="sac long-poll listen daemon",
            restart_policy="always",
        )
    ]


# ---------------------------------------------------------------------------
# find_service_job
# ---------------------------------------------------------------------------


def test_find_service_job_resolves_from_provider():
    # Arrange
    kwargs = dict(extra_providers=[_svc_provider])
    # Act
    job = _ensure.find_service_job("sac.listen", **kwargs)
    # Assert
    assert job.command == "sac listen --port 7878"


def test_find_service_job_unknown_raises_keyerror():
    # Arrange
    kwargs = dict(extra_providers=[_svc_provider])
    # Act
    # Assert
    with pytest.raises(KeyError):
        _ensure.find_service_job("no.such", **kwargs)


# ---------------------------------------------------------------------------
# backend selection
# ---------------------------------------------------------------------------


def test_ensure_picks_systemd_when_available(tmp_path):
    # Arrange
    run = _Recorder()
    # Act
    result = _ensure.ensure_service(
        "sac.listen",
        home=tmp_path,
        systemd_available_fn=lambda: True,
        run_fn=run,
        discover_kwargs={"extra_providers": [_svc_provider]},
    )
    # Assert
    assert result.backend == "systemd"


def test_ensure_picks_respawn_when_systemd_absent(tmp_path):
    # Arrange
    spawned = []
    # Act
    result = _ensure.ensure_service(
        "sac.listen",
        home=tmp_path,
        systemd_available_fn=lambda: False,
        spawn_fn=lambda script, logf: (spawned.append(script) or 4_242),
        discover_kwargs={"extra_providers": [_svc_provider]},
    )
    # Assert
    assert result.backend == "respawn"


# ---------------------------------------------------------------------------
# systemd backend install sequence
# ---------------------------------------------------------------------------


def test_ensure_systemd_writes_unit_file(tmp_path):
    # Arrange
    run = _Recorder()
    # Act
    result = _ensure.ensure_service(
        "sac.listen",
        home=tmp_path,
        systemd_available_fn=lambda: True,
        run_fn=run,
        discover_kwargs={"extra_providers": [_svc_provider]},
    )
    # Assert
    assert result.unit_path.exists()


def test_ensure_systemd_unit_lands_under_user_unit_dir(tmp_path):
    # Arrange
    run = _Recorder()
    # Act
    result = _ensure.ensure_service(
        "sac.listen",
        home=tmp_path,
        systemd_available_fn=lambda: True,
        run_fn=run,
        discover_kwargs={"extra_providers": [_svc_provider]},
    )
    # Assert
    assert result.unit_path == (
        tmp_path / ".config" / "systemd" / "user" / "sac.listen.service"
    )


def test_ensure_systemd_runs_daemon_reload(tmp_path):
    # Arrange
    run = _Recorder()
    # Act
    _ensure.ensure_service(
        "sac.listen",
        home=tmp_path,
        systemd_available_fn=lambda: True,
        run_fn=run,
        discover_kwargs={"extra_providers": [_svc_provider]},
    )
    # Assert
    assert ["systemctl", "--user", "daemon-reload"] in run.calls


def test_ensure_systemd_runs_enable_now(tmp_path):
    # Arrange
    run = _Recorder()
    # Act
    _ensure.ensure_service(
        "sac.listen",
        home=tmp_path,
        systemd_available_fn=lambda: True,
        run_fn=run,
        discover_kwargs={"extra_providers": [_svc_provider]},
    )
    # Assert
    assert [
        "systemctl",
        "--user",
        "enable",
        "--now",
        "sac.listen.service",
    ] in run.calls


# ---------------------------------------------------------------------------
# respawn backend install sequence
# ---------------------------------------------------------------------------


def test_ensure_respawn_writes_script(tmp_path):
    # Arrange
    calls = []
    # Act
    result = _ensure.ensure_service(
        "sac.listen",
        home=tmp_path,
        systemd_available_fn=lambda: False,
        spawn_fn=lambda script, logf: (calls.append(script) or 1),
        discover_kwargs={"extra_providers": [_svc_provider]},
    )
    # Assert
    assert result.script_path.exists()


def test_ensure_respawn_writes_alive_flag(tmp_path):
    # Arrange
    from scitex_dev.jobs import _respawn as rs

    job = _svc_provider()[0]
    # Act
    _ensure.ensure_service(
        "sac.listen",
        home=tmp_path,
        systemd_available_fn=lambda: False,
        spawn_fn=lambda script, logf: 1,
        discover_kwargs={"extra_providers": [_svc_provider]},
    )
    # Assert
    assert rs.flag_path(job, home=tmp_path).exists()


def test_ensure_respawn_launches_supervisor(tmp_path):
    # Arrange
    spawned = []
    # Act
    _ensure.ensure_service(
        "sac.listen",
        home=tmp_path,
        systemd_available_fn=lambda: False,
        spawn_fn=lambda script, logf: (spawned.append((script, logf)) or 7),
        discover_kwargs={"extra_providers": [_svc_provider]},
    )
    # Assert
    assert len(spawned) == 1


def test_ensure_respawn_idempotent_when_supervisor_running(tmp_path):
    # Arrange — write a pidfile naming THIS process (guaranteed alive).
    import os

    from scitex_dev.jobs import _respawn as rs

    job = _svc_provider()[0]
    pidf = rs.pidfile_path(job, home=tmp_path)
    pidf.parent.mkdir(parents=True, exist_ok=True)
    pidf.write_text(str(os.getpid()), encoding="utf-8")
    spawned = []
    # Act
    result = _ensure.ensure_service(
        "sac.listen",
        home=tmp_path,
        systemd_available_fn=lambda: False,
        spawn_fn=lambda script, logf: (spawned.append(script) or 1),
        discover_kwargs={"extra_providers": [_svc_provider]},
    )
    # Assert — no second supervisor launched.
    assert result.already_running and spawned == []


# ---------------------------------------------------------------------------
# systemd_user_available probe
# ---------------------------------------------------------------------------


def test_systemd_available_true_when_manager_answers():
    # Arrange
    class _R:
        returncode = 1
        stdout = "degraded\n"

    # Act
    avail = _ensure.systemd_user_available(run_fn=lambda argv: _R())
    # Assert — a state word means the user manager answered.
    assert avail is True


def test_systemd_available_false_when_no_output():
    # Arrange
    class _R:
        returncode = 1
        stdout = ""

    # Act
    avail = _ensure.systemd_user_available(run_fn=lambda argv: _R())
    # Assert
    assert avail is False


def test_systemd_available_false_when_binary_missing():
    # Arrange
    def _boom(argv):
        raise FileNotFoundError("systemctl")

    # Act
    avail = _ensure.systemd_user_available(run_fn=_boom)
    # Assert
    assert avail is False


# EOF
