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


# ---------------------------------------------------------------------------
# worktree-gc — the third registered job. Pins the registry shape per the
# §3 "Adding a new job" checklist in the cron-management skill: every new
# entry must come with a test that asserts the schedule + command + log
# path exactly so a typo in the registry can't ship silently.
# ---------------------------------------------------------------------------


def test_registry_has_worktree_gc_entry():
    # Arrange
    # Act
    # Assert
    assert "worktree-gc" in _jobs.JOB_REGISTRY


def test_worktree_gc_name_matches_registry_key():
    # Arrange
    # Act
    spec = _jobs.get_job("worktree-gc")
    # Assert
    assert spec.name == "worktree-gc"


def test_worktree_gc_schedule_is_every_six_hours():
    # Arrange
    # Act
    spec = _jobs.get_job("worktree-gc")
    # Assert
    assert spec.schedule == "0 */6 * * *"


def test_worktree_gc_command_invokes_scitex_dev_cron_exec():
    # Arrange
    # Act
    spec = _jobs.get_job("worktree-gc")
    # Assert
    assert "scitex-dev cron exec worktree-gc" in spec.command


def test_worktree_gc_command_writes_to_named_log_file():
    # Arrange
    # Act
    spec = _jobs.get_job("worktree-gc")
    # Assert
    assert "/.scitex/dev/logs/cron-worktree-gc.log" in spec.command


def test_worktree_gc_description_mentions_managed_segment():
    # Arrange
    # Act
    spec = _jobs.get_job("worktree-gc")
    # Assert — the guardrail must be obvious from the registry alone, so
    # `scitex-dev cron list` shows operators which directory is touched.
    assert ".claude/worktrees" in spec.description


# ---------------------------------------------------------------------------
# task-harvest — the fourth registered job (scitex-dev cron PR follow-up to
# scitex-todo PR #72; operator commissioned the skill in TG msgs 325/327/
# 332/335). Pins the registry shape per the §3 "Adding a new job" checklist
# so a typo in the schedule / command / log path can't ship silently.
# ---------------------------------------------------------------------------


def test_registry_has_task_harvest_entry():
    # Arrange
    # Act
    # Assert
    assert "task-harvest" in _jobs.JOB_REGISTRY


def test_task_harvest_name_matches_registry_key():
    # Arrange
    # Act
    spec = _jobs.get_job("task-harvest")
    # Assert
    assert spec.name == "task-harvest"


def test_task_harvest_schedule_is_every_six_hours():
    # Arrange
    # Act
    spec = _jobs.get_job("task-harvest")
    # Assert
    assert spec.schedule == "0 */6 * * *"


def test_task_harvest_command_invokes_scitex_dev_cron_exec():
    # Arrange
    # Act
    spec = _jobs.get_job("task-harvest")
    # Assert
    assert "scitex-dev cron exec task-harvest" in spec.command


def test_task_harvest_command_writes_to_named_log_file():
    # Arrange
    # Act
    spec = _jobs.get_job("task-harvest")
    # Assert
    assert "/.scitex/dev/logs/cron-task-harvest.log" in spec.command


def test_task_harvest_description_mentions_tasks_yaml():
    # Arrange
    # Act
    spec = _jobs.get_job("task-harvest")
    # Assert — the operator's mental model is "the shared board" =
    # ~/.scitex/todo/tasks.yaml; `scitex-dev cron list` should surface
    # that the harvest touches the board so operators can tell apart
    # task-harvest from the other (host-local) cron jobs.
    assert "tasks.yaml" in spec.description


def test_list_jobs_includes_task_harvest():
    # Arrange
    # Act
    names = [s.name for s in _jobs.list_jobs()]
    # Assert
    assert "task-harvest" in names


# ---------------------------------------------------------------------------
# cred-distribute — the fifth registered job. Subsumes the operator's host-
# side `~/.scitex/push-freshest-cred-to-spartan.sh` per directive 2026-06-11.
# Pins the registry shape per the §3 "Adding a new job" checklist so a typo
# in the schedule / command / log path can't ship silently.
# ---------------------------------------------------------------------------


def test_registry_has_cred_distribute_entry():
    # Arrange
    # Act
    # Assert
    assert "cred-distribute" in _jobs.JOB_REGISTRY


def test_cred_distribute_name_matches_registry_key():
    # Arrange
    # Act
    spec = _jobs.get_job("cred-distribute")
    # Assert
    assert spec.name == "cred-distribute"


def test_cred_distribute_schedule_is_every_two_hours_on_the_hour():
    # Arrange
    # Act
    spec = _jobs.get_job("cred-distribute")
    # Assert — matches the operator's spartan-cred-push cadence.
    assert spec.schedule == "0 */2 * * *"


def test_cred_distribute_command_invokes_scitex_dev_cron_exec():
    # Arrange
    # Act
    spec = _jobs.get_job("cred-distribute")
    # Assert
    assert "scitex-dev cron exec cred-distribute" in spec.command


def test_cred_distribute_command_writes_to_named_log_file():
    # Arrange
    # Act
    spec = _jobs.get_job("cred-distribute")
    # Assert
    assert "/.scitex/dev/logs/cron-cred-distribute.log" in spec.command


def test_cred_distribute_description_mentions_sac_distribute_verb():
    # Arrange
    # Act
    spec = _jobs.get_job("cred-distribute")
    # Assert — `scitex-dev cron list` should make obvious what shells out.
    assert "sac accounts distribute" in spec.description


def test_cred_distribute_description_mentions_config_path():
    # Arrange
    # Act
    spec = _jobs.get_job("cred-distribute")
    # Assert — operator needs to find the YAML knob without reading source.
    assert "cred-distribute.yaml" in spec.description


def test_list_jobs_includes_cred_distribute():
    # Arrange
    # Act
    names = [s.name for s in _jobs.list_jobs()]
    # Assert
    assert "cred-distribute" in names


# EOF


# -- spartan-conn-monitor ---------------------------------------------------


def test_registry_has_spartan_conn_monitor_entry():
    # Arrange
    # Act
    # Assert
    assert "spartan-conn-monitor" in _jobs.JOB_REGISTRY


def test_spartan_conn_monitor_schedule_is_every_thirty_minutes():
    # Arrange
    # Act
    spec = _jobs.get_job("spartan-conn-monitor")
    # Assert
    assert spec.schedule == "*/30 * * * *"


def test_spartan_conn_monitor_command_invokes_scitex_dev_cron_exec():
    # Arrange
    # Act
    spec = _jobs.get_job("spartan-conn-monitor")
    # Assert
    assert "scitex-dev cron exec spartan-conn-monitor" in spec.command


def test_spartan_conn_monitor_command_writes_to_log_under_scitex_dev():
    # Arrange
    # Act
    spec = _jobs.get_job("spartan-conn-monitor")
    # Assert
    assert "/.scitex/dev/logs/cron-spartan-conn-monitor.log" in spec.command
