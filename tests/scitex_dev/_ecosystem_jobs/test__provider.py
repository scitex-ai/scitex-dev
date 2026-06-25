"""The ecosystem-jobs provider roster.

Pins the operator-mandated ecosystem self-pull: a central timer that keeps
every managed checkout's develop current via the non-destructive
``ecosystem sync`` sweep.
"""

from __future__ import annotations

from scitex_dev._ecosystem_jobs._provider import provide_jobs


def test_provider_registers_the_self_pull_timer():
    """The self-pull job is registered as a systemd timer (boot + periodic)."""
    # Arrange
    timer_names = {job.name for job in provide_jobs() if job.kind == "timer"}
    # Act
    registered = "ecosystem-self-pull" in timer_names
    # Assert
    assert registered


def test_self_pull_runs_the_ff_only_sync_sweep():
    """The timer drives the existing ff-only `ecosystem sync` (never clobbers)."""
    # Arrange
    by_name = {job.name: job for job in provide_jobs()}
    # Act
    command = by_name["ecosystem-self-pull"].command
    # Assert
    assert "ecosystem sync --yes" in command
