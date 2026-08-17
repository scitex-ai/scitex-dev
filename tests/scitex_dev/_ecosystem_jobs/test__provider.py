"""The ecosystem-jobs provider roster.

Pins the operator-mandated ecosystem self-pull: a central timer that keeps
every managed checkout's develop current via the non-destructive
``ecosystem sync`` sweep.
"""

from __future__ import annotations

from scitex_dev._ecosystem_jobs._provider import (
    JOB_SHELL_BODIES,
    log_path_for,
    provide_jobs,
)


def test_provider_registers_the_self_pull_timer():
    """The self-pull job is registered as a systemd timer (boot + periodic)."""
    # Arrange
    timer_names = {job.name for job in provide_jobs() if job.kind == "timer"}
    # Act
    registered = "scitex-dev-ecosystem-self-pull" in timer_names
    # Assert
    assert registered


def test_self_pull_command_is_the_bare_exec_verb():
    """The verb owns logging (#367), so command is the bare `cron exec` line."""
    # Arrange
    by_name = {job.name: job for job in provide_jobs()}
    # Act
    command = by_name["scitex-dev-ecosystem-self-pull"].command
    # Assert
    assert command == "scitex-dev ecosystem cron exec scitex-dev-ecosystem-self-pull"


def test_self_pull_body_runs_the_ff_only_sync_sweep():
    """The pure shell body drives the existing ff-only `ecosystem sync`."""
    # Arrange
    # Act
    body = JOB_SHELL_BODIES["scitex-dev-ecosystem-self-pull"]
    # Assert
    assert "ecosystem sync --yes" in body


def test_self_pull_logs_under_runtime_logs():
    """The job's log resolves under `runtime/logs/`, never `dev/logs/`."""
    # Arrange
    # Act
    log = log_path_for("scitex-dev-ecosystem-self-pull").as_posix()
    # Assert
    assert log.endswith(".scitex/dev/runtime/logs/timer-ecosystem-self-pull.log")


def test_provider_registers_the_drift_report_timer():
    """The unified drift observer is registered as a periodic timer."""
    # Arrange
    timer_names = {job.name for job in provide_jobs() if job.kind == "timer"}
    # Act
    registered = "scitex-dev-drift-report" in timer_names
    # Assert
    assert registered


def test_drift_report_body_runs_the_ecosystem_drift_report():
    """The pure shell body drives the read-only `ecosystem drift-report`."""
    # Arrange
    # Act
    body = JOB_SHELL_BODIES["scitex-dev-drift-report"]
    # Assert
    assert "ecosystem drift-report" in body


def test_drift_report_command_is_the_bare_exec_verb():
    """The timer's ExecStart is the bare `cron exec` line (verb owns logging)."""
    # Arrange
    by_name = {job.name: job for job in provide_jobs()}
    # Act
    command = by_name["scitex-dev-drift-report"].command
    # Assert
    assert command == "scitex-dev ecosystem cron exec scitex-dev-drift-report"


def test_drift_report_timer_cadence_is_conservative_six_hours():
    """Schedule stays conservative (6h) per the spec — not a PyPI-thrash loop."""
    # Arrange
    by_name = {job.name: job for job in provide_jobs()}
    # Act
    cadence = by_name["scitex-dev-drift-report"].on_unit_active_sec
    # Assert
    assert cadence == "6h"


def test_provider_registers_the_pr_expire_cron():
    """The fleet PR-expiry primitive is registered as a daily cron job."""
    # Arrange
    cron_names = {job.name for job in provide_jobs() if job.kind == "cron"}
    # Act
    registered = "scitex-dev-pr-expire" in cron_names
    # Assert
    assert registered


def test_pr_expire_body_ships_in_dry_run_mode():
    """SAFETY: the scheduled job runs in --dry-run — no auto-mass-close."""
    # Arrange
    # Act
    body = JOB_SHELL_BODIES["scitex-dev-pr-expire"]
    # Assert
    assert "--dry-run" in body


def test_pr_expire_body_does_not_apply():
    """SAFETY: the scheduled job must NOT pass --apply on first fire."""
    # Arrange
    # Act
    body = JOB_SHELL_BODIES["scitex-dev-pr-expire"]
    # Assert
    assert "--apply" not in body


def test_pr_expire_body_runs_the_ecosystem_pr_expire_primitive():
    """The cron drives `ecosystem pr expire --all` across the fleet."""
    # Arrange
    # Act
    body = JOB_SHELL_BODIES["scitex-dev-pr-expire"]
    # Assert
    assert "ecosystem pr expire --all" in body
