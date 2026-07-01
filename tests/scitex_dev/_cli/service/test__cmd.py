#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for ``scitex-dev service ensure``.

These tests never spawn a real supervisor: the unknown-name path exits
before any backend runs, and the idempotent path pre-seeds a live
pidfile (this test process) so the respawn backend short-circuits.
"""

from __future__ import annotations

import os

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev.jobs import _respawn as rs


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_home(tmp_path):
    prev = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        yield tmp_path
    finally:
        if prev is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = prev


def test_service_group_help_lists_ensure(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["service", "--help"])
    # Assert
    assert "ensure" in result.output


def test_service_ensure_unknown_name_errors(runner, installed_job_provider):
    # Arrange
    # Act
    result = runner.invoke(main, ["service", "ensure", "no.such.service"])
    # Assert
    assert result.exit_code != 0


def test_service_ensure_unknown_name_message_names_it(
    runner, installed_job_provider
):
    # Arrange
    # Act
    result = runner.invoke(main, ["service", "ensure", "no.such.service"])
    # Assert
    assert "no.such.service" in result.output


def _seed_live_pidfile(job_name, home):
    """Pre-seed a pidfile naming THIS process so the respawn backend
    treats the supervisor as already-running and does not spawn one.
    """
    from scitex_dev.jobs import JobSpec

    job = JobSpec(
        name=job_name,
        kind="service",
        schedule="",
        command="echo testpkg-service",
        description="test",
        restart_policy="on-failure",
    )
    pidf = rs.pidfile_path(job, home=home)
    pidf.parent.mkdir(parents=True, exist_ok=True)
    pidf.write_text(str(os.getpid()), encoding="utf-8")
    return job


def test_service_ensure_respawn_idempotent_reports_running(
    runner, installed_job_provider, temp_home
):
    # Arrange — testpkg.svc is a kind=service job from the fixture.
    _seed_live_pidfile("testpkg.svc", temp_home)
    # Act
    result = runner.invoke(
        main, ["service", "ensure", "testpkg.svc", "--respawn"]
    )
    # Assert
    assert result.exit_code == 0


def test_service_ensure_respawn_idempotent_backend_is_respawn(
    runner, installed_job_provider, temp_home
):
    # Arrange
    _seed_live_pidfile("testpkg.svc", temp_home)
    # Act
    result = runner.invoke(
        main, ["service", "ensure", "testpkg.svc", "--respawn"]
    )
    # Assert
    assert "backend=respawn" in result.output


def test_service_ensure_respawn_idempotent_json_backend(
    runner, installed_job_provider, temp_home
):
    # Arrange
    import json

    _seed_live_pidfile("testpkg.svc", temp_home)
    # Act
    result = runner.invoke(
        main, ["service", "ensure", "testpkg.svc", "--respawn", "--json"]
    )
    # Assert
    assert json.loads(result.output)["backend"] == "respawn"


def test_service_ensure_respawn_idempotent_json_already_running(
    runner, installed_job_provider, temp_home
):
    # Arrange
    import json

    _seed_live_pidfile("testpkg.svc", temp_home)
    # Act
    result = runner.invoke(
        main, ["service", "ensure", "testpkg.svc", "--respawn", "--json"]
    )
    # Assert
    assert json.loads(result.output)["already_running"] is True


# EOF
