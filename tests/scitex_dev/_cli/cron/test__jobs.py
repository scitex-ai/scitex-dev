"""Unit tests pinning the cron job registry."""

from __future__ import annotations

import pytest

from scitex_dev._cli.cron import _jobs


def test_registry_has_ci_watch_entry():
    # Arrange
    # Act
    # Assert
    assert "ci-watch" in _jobs.JOB_REGISTRY


def test_ci_watch_schedule_is_every_ten_minutes():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-watch")
    # Assert
    assert spec.schedule == "*/10 * * * *"


def test_ci_watch_command_invokes_scitex_dev_cron_exec():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-watch")
    # Assert
    assert "scitex-dev cron exec ci-watch" in spec.command


def test_ci_watch_command_writes_to_log_under_scitex_dev():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-watch")
    # Assert
    assert "/.scitex/dev/logs/cron-ci-watch.log" in spec.command


def test_ci_watch_description_non_empty():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-watch")
    # Assert
    assert spec.description.strip() != ""


def test_get_job_raises_on_unknown_name():
    # Arrange
    # Act
    # Assert
    with pytest.raises(KeyError):
        _jobs.get_job("does-not-exist")


def test_list_jobs_includes_ci_watch():
    # Arrange
    # Act
    names = [s.name for s in _jobs.list_jobs()]
    # Assert
    assert "ci-watch" in names


# EOF
