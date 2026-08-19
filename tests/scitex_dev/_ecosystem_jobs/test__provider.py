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


# --------------------------------------------------------------------------- #
# venv-refresh must reach EVERY package venv, and must be able to fail         #
# --------------------------------------------------------------------------- #
#
# Operator rule, 2026-08-19, stated as global: "cd ~/proj/xxx && source
# .venv/bin/activate && uv pip install -Ue .[all] must be done periodically;
# especially when the package updated ... in any place in any host", and
# "they must have self-update system turned on ... especially for the ones
# with EDITABLE installation".
#
# The job previously passed `--venv current` for every pass, which refreshes
# only the interpreter the job happens to run under. Measured on
# ywata-note-win: three green runs in one day while the operator's own venv
# sat 6 minor versions behind and needed 56 packages moved by hand.


def _venv_refresh_body() -> str:
    from scitex_dev._ecosystem_jobs._provider import JOB_SHELL_BODIES

    return JOB_SHELL_BODIES["scitex-dev-venv-refresh"]


def test_venv_refresh_targets_every_package_venv():
    # Arrange — `per-package` is `ecosystem install`'s DEFAULT and creates or
    # refreshes ~/proj/<pkg>/.venv for every package. Asserting on the flag
    # rather than on "not current" because the flag is the thing that reaches
    # the other venvs; a body with neither flag would silently inherit the
    # default and pass a negative assertion.
    # Act
    body = _venv_refresh_body()
    # Assert
    assert "--venv per-package" in body


def test_venv_refresh_still_refreshes_the_shared_runtime_venv():
    # Arrange — agents EXECUTE from the shared venv, so dropping `current`
    # entirely would fix the operator's venv and break the fleet's. Both
    # populations are refreshed; this test exists so a future simplification
    # that deletes one notices it is deleting a population.
    # Act
    body = _venv_refresh_body()
    # Assert
    assert "--venv current" in body


def test_venv_refresh_cannot_swallow_a_failed_install():
    # Arrange — THE LOAD-BEARING ONE. With `|| true` the unit reported success
    # three times while installing into a venv nobody uses. An observe job may
    # use `|| true` (a drift FINDING is data, not a unit failure); this job
    # INSTALLS, and a failed install is a failure.
    # Act
    body = _venv_refresh_body()
    # Assert
    assert "|| true" not in body


def test_venv_refresh_stops_at_the_first_failing_pass():
    # Arrange — three passes chained with `;` would run passes 2 and 3 after
    # pass 1 died, and the exit code would be pass 3's. `set -e` makes the
    # first failure the job's failure.
    # Act
    body = _venv_refresh_body()
    # Assert
    assert body.startswith("set -e; ")


def test_venv_refresh_upgrades_dependencies_not_only_the_package():
    # Arrange — an EDITABLE install tracks a moving checkout, so the package
    # is current by construction while its DEPENDENCIES rot. That gap is what
    # the operator hit: 56 packages moved by a manual `uv pip install -Ue`.
    # Act
    body = _venv_refresh_body()
    # Assert
    assert "--upgrade" in body and "--extras all" in body
