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


# -- spartan-conn-monitor: EMAIL channel (config-layer prefix mapping) -------
# The monitor SOURCE must never read a foreign prefix; the cross-package value
# reuse that wires the proven SCITEX_UI_EMAIL_* creds onto the email backend's
# SCITEX_NOTIFICATION_EMAIL_* API lives HERE, in the materialised crontab line.
# These tests pin that mapping so a typo can't silently break the email alert.


def test_spartan_conn_monitor_command_sources_the_ui_secrets_file():
    # Arrange
    # Act — the line must pull in the file where SCITEX_UI_EMAIL_* live.
    spec = _jobs.get_job("spartan-conn-monitor")
    # Assert — POSIX `.` source of the 01_ui.src secrets file.
    assert ". " in spec.command and "01_ui.src" in spec.command


def test_spartan_conn_monitor_command_guards_the_source_with_file_test():
    # Arrange
    # Act — a missing secrets file must not break the cron tick.
    spec = _jobs.get_job("spartan-conn-monitor")
    # Assert — the source is guarded by a `[ -f ... ]` existence test.
    assert "[ -f " in spec.command


def test_spartan_conn_monitor_command_maps_email_from():
    # Arrange
    # Act
    spec = _jobs.get_job("spartan-conn-monitor")
    # Assert — backend FROM <= UI agent address.
    assert "SCITEX_NOTIFICATION_EMAIL_FROM=$SCITEX_UI_EMAIL_AGENT" in spec.command


def test_spartan_conn_monitor_command_maps_email_password():
    # Arrange
    # Act
    spec = _jobs.get_job("spartan-conn-monitor")
    # Assert — backend PASSWORD <= UI agent password (with base-password fallback).
    assert (
        "SCITEX_NOTIFICATION_EMAIL_PASSWORD="
        "${SCITEX_UI_EMAIL_AGENT_PASSWORD:-$SCITEX_UI_EMAIL_PASSWORD}"
    ) in spec.command


def test_spartan_conn_monitor_command_maps_smtp_host():
    # Arrange
    # Act
    spec = _jobs.get_job("spartan-conn-monitor")
    # Assert — backend SMTP host <= UI SMTP server.
    assert (
        "SCITEX_NOTIFICATION_EMAIL_SMTP_HOST=$SCITEX_UI_EMAIL_SMTP_SERVER"
        in spec.command
    )


def test_spartan_conn_monitor_command_maps_smtp_port():
    # Arrange
    # Act
    spec = _jobs.get_job("spartan-conn-monitor")
    # Assert — backend SMTP port <= UI SMTP port.
    assert (
        "SCITEX_NOTIFICATION_EMAIL_SMTP_PORT=$SCITEX_UI_EMAIL_SMTP_PORT" in spec.command
    )


def test_spartan_conn_monitor_command_recipient_uses_dev_prefixed_knob():
    # Arrange
    # Act — per the prefix rule, the recipient is THIS package's own knob.
    spec = _jobs.get_job("spartan-conn-monitor")
    # Assert
    assert "${SCITEX_DEV_SPARTAN_MONITOR_EMAIL_TO:-" in spec.command


def test_spartan_conn_monitor_command_recipient_defaults_to_operator():
    # Arrange
    # Act
    spec = _jobs.get_job("spartan-conn-monitor")
    # Assert — operator's unimelb address is the default recipient.
    assert "Yusuke.Watanabe@unimelb.edu.au" in spec.command


def test_spartan_conn_monitor_command_exports_before_exec():
    # Arrange
    spec = _jobs.get_job("spartan-conn-monitor")
    # Act — the env mapping must be set BEFORE the monitor runs.
    export_at = spec.command.index("SCITEX_NOTIFICATION_EMAIL_FROM")
    exec_at = spec.command.index("scitex-dev cron exec spartan-conn-monitor")
    # Assert
    assert export_at < exec_at


def test_spartan_conn_monitor_command_has_no_foreign_notification_prefix_leak():
    # Arrange — sanity: the SOURCE module never references a foreign prefix; this
    # pins that the mapping lives ONLY in the config line (this command string).
    import inspect

    from scitex_dev._cli.cron import _spartan_conn_monitor as srcmod

    source = inspect.getsource(srcmod)
    # Act
    leaks = [
        tok for tok in ("SCITEX_UI_EMAIL", "SCITEX_NOTIFICATION_EMAIL") if tok in source
    ]
    # Assert — zero foreign-prefix tokens in the monitor source.
    assert leaks == []
