#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the respawn-loop supervisor builders."""

from __future__ import annotations

from pathlib import Path

from scitex_dev.jobs import JobSpec
from scitex_dev.jobs import _respawn as rs


def _svc(**overrides):
    base = dict(
        name="sac.listen",
        kind="service",
        schedule="",
        command="sac listen --port 7878",
        description="sac long-poll listen daemon",
        restart_policy="always",
    )
    base.update(overrides)
    return JobSpec(**base)


def test_package_of_uses_prefix_before_first_dot():
    # Arrange
    job = _svc(name="sac.listen")
    # Act
    pkg = rs.package_of(job)
    # Assert
    assert pkg == "sac"


def test_package_of_bare_name_keys_under_itself():
    # Arrange
    job = _svc(name="ci-watch")
    # Act
    pkg = rs.package_of(job)
    # Assert
    assert pkg == "ci-watch"


def test_runtime_dir_is_under_scitex_pkg_runtime(tmp_path):
    # Arrange
    job = _svc()
    # Act
    rt = rs.runtime_dir(job, home=tmp_path)
    # Assert
    assert rt == tmp_path / ".scitex" / "sac" / "runtime"


def test_log_path_is_under_runtime_logs(tmp_path):
    # Arrange
    job = _svc()
    # Act
    log = rs.log_path(job, home=tmp_path)
    # Assert — operator directive: logs live under runtime/logs/, NOT
    # ~/.scitex/dev/logs/.
    assert log == tmp_path / ".scitex" / "sac" / "runtime" / "logs" / "sac.listen.log"


def test_log_path_not_under_bare_logs_dir(tmp_path):
    # Arrange
    job = _svc()
    # Act
    log = rs.log_path(job, home=tmp_path)
    # Assert
    assert "runtime" in log.parts and log.parts.index("runtime") < log.parts.index(
        "logs"
    )


def test_flag_path_under_runtime(tmp_path):
    # Arrange
    job = _svc()
    # Act
    flag = rs.flag_path(job, home=tmp_path)
    # Assert
    assert flag == tmp_path / ".scitex" / "sac" / "runtime" / "sac.listen.alive"


def test_pidfile_path_under_runtime(tmp_path):
    # Arrange
    job = _svc()
    # Act
    pidf = rs.pidfile_path(job, home=tmp_path)
    # Assert
    assert pidf == tmp_path / ".scitex" / "sac" / "runtime" / "sac.listen.pid"


def test_script_has_shebang(tmp_path):
    # Arrange
    job = _svc()
    # Act
    text = rs.build_respawn_script(job, home=tmp_path)
    # Assert
    assert text.startswith("#!/bin/bash")


def test_script_loops_while_alive_flag_exists(tmp_path):
    # Arrange
    job = _svc()
    # Act
    text = rs.build_respawn_script(job, home=tmp_path)
    # Assert
    assert 'while [ -e "$FLAG" ]; do' in text


def test_script_includes_backoff_and_cap(tmp_path):
    # Arrange
    job = _svc()
    # Act
    text = rs.build_respawn_script(
        job, home=tmp_path, backoff_start=5, backoff_max=300
    )
    # Assert
    assert "backoff=5" in text and "max_backoff=300" in text


def test_script_absolutises_execstart_or_env_falls_back(tmp_path):
    # Arrange — the resolved command must appear on the run line so a
    # detached loop with a minimal env still finds the binary.
    job = _svc(command="/opt/sac/bin/sac listen")
    # Act
    text = rs.build_respawn_script(job, home=tmp_path)
    # Assert — absolute command passes through resolve_execstart verbatim.
    assert "/opt/sac/bin/sac listen" in text


def test_script_writes_pidfile(tmp_path):
    # Arrange
    job = _svc()
    # Act
    text = rs.build_respawn_script(job, home=tmp_path)
    # Assert
    assert 'echo "$$" >"$PIDFILE"' in text


def test_script_traps_term_for_cleanup(tmp_path):
    # Arrange
    job = _svc()
    # Act
    text = rs.build_respawn_script(job, home=tmp_path)
    # Assert
    assert "trap cleanup INT TERM" in text


def test_script_references_runtime_log_path(tmp_path):
    # Arrange
    job = _svc()
    logf = rs.log_path(job, home=tmp_path)
    # Act
    text = rs.build_respawn_script(job, home=tmp_path)
    # Assert
    assert str(logf) in text


# EOF
