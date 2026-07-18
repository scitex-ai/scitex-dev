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


# ---------------------------------------------------------------------------
# creds-rotate-all — federates the operator's ad-hoc
# `# scitex-dev creds-rotate (managed)` crontab line (the default
# `scitex-dev creds rotate-all --yes` install at "0 * * * *", see
# _creds._cron) into the managed block. Pins the registry shape per the
# §3 "Adding a new job" checklist so a typo in schedule / command / log
# path can't ship silently.
# ---------------------------------------------------------------------------


def test_registry_has_creds_rotate_all_entry():
    # Arrange
    # Act
    # Assert
    assert "creds-rotate-all" in _jobs.JOB_REGISTRY


def test_creds_rotate_all_name_matches_registry_key():
    # Arrange
    # Act
    spec = _jobs.get_job("creds-rotate-all")
    # Assert
    assert spec.name == "creds-rotate-all"


def test_creds_rotate_all_schedule_is_top_of_every_hour():
    # Arrange
    # Act
    spec = _jobs.get_job("creds-rotate-all")
    # Assert — matches _creds._cron._interval_to_schedule(60).
    assert spec.schedule == "0 * * * *"


def test_creds_rotate_all_command_invokes_creds_rotate_all_yes():
    # Arrange
    # Act
    spec = _jobs.get_job("creds-rotate-all")
    # Assert
    assert "scitex-dev creds rotate-all --yes" in spec.command


def test_creds_rotate_all_command_writes_to_creds_rotate_log():
    # Arrange
    # Act
    spec = _jobs.get_job("creds-rotate-all")
    # Assert — the ad-hoc line this entry retires writes to exactly this
    # path (NO `cron-` prefix); dashboards tailing it must keep working.
    assert "/.scitex/dev/logs/creds-rotate.log" in spec.command


def test_creds_rotate_all_command_keeps_one_mib_rotation_threshold():
    # Arrange
    # Act
    spec = _jobs.get_job("creds-rotate-all")
    # Assert — the 1-MiB rotate-to-.1 threshold from the ad-hoc installer
    # (_creds._cron.build_cron_line) is preserved in the managed line.
    assert "1048576" in spec.command


def test_creds_rotate_all_command_keeps_stat_size_check():
    # Arrange
    # Act
    spec = _jobs.get_job("creds-rotate-all")
    # Assert — the `stat -c%s` size probe of the rotation guard survives.
    assert "stat -c%s" in spec.command


def test_creds_rotate_all_description_mentions_rotate_all_verb():
    # Arrange
    # Act
    spec = _jobs.get_job("creds-rotate-all")
    # Assert
    assert "rotate-all" in spec.description


def test_list_jobs_includes_creds_rotate_all():
    # Arrange
    # Act
    names = [s.name for s in _jobs.list_jobs()]
    # Assert
    assert "creds-rotate-all" in names


# ---------------------------------------------------------------------------
# ci-runner-ensure — federates the operator's ad-hoc ci-runner-ensure
# crontab line (every 30 min, body = ~/.scitex/dev/ci-runner-ensure-cron.sh)
# into the managed block. Pins schedule / command / log path.
# ---------------------------------------------------------------------------


def test_registry_has_ci_runner_ensure_entry():
    # Arrange
    # Act
    # Assert
    assert "ci-runner-ensure" in _jobs.JOB_REGISTRY


def test_ci_runner_ensure_name_matches_registry_key():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-runner-ensure")
    # Assert
    assert spec.name == "ci-runner-ensure"


def test_ci_runner_ensure_schedule_is_every_thirty_minutes():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-runner-ensure")
    # Assert
    assert spec.schedule == "*/30 * * * *"


def test_ci_runner_ensure_command_runs_the_host_script():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-runner-ensure")
    # Assert
    assert "$HOME/.scitex/dev/ci-runner-ensure-cron.sh" in spec.command


def test_ci_runner_ensure_command_writes_to_named_log_file():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-runner-ensure")
    # Assert
    assert "/.scitex/dev/logs/ci-runner-ensure.log" in spec.command


def test_ci_runner_ensure_description_non_empty():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-runner-ensure")
    # Assert
    assert spec.description.strip() != ""


def test_list_jobs_includes_ci_runner_ensure():
    # Arrange
    # Act
    names = [s.name for s in _jobs.list_jobs()]
    # Assert
    assert "ci-runner-ensure" in names


# ---------------------------------------------------------------------------
# ci-runner-workgc — federates the operator's ad-hoc ci-runner-workgc
# crontab line (every 6 h, body = ~/.scitex/dev/ci-runner-workgc-cron.sh)
# into the managed block. Pins schedule / command / log path.
# ---------------------------------------------------------------------------


def test_registry_has_ci_runner_workgc_entry():
    # Arrange
    # Act
    # Assert
    assert "ci-runner-workgc" in _jobs.JOB_REGISTRY


def test_ci_runner_workgc_name_matches_registry_key():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-runner-workgc")
    # Assert
    assert spec.name == "ci-runner-workgc"


def test_ci_runner_workgc_schedule_is_every_six_hours():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-runner-workgc")
    # Assert
    assert spec.schedule == "0 */6 * * *"


def test_ci_runner_workgc_command_runs_the_host_script():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-runner-workgc")
    # Assert
    assert "$HOME/.scitex/dev/ci-runner-workgc-cron.sh" in spec.command


def test_ci_runner_workgc_command_writes_to_named_log_file():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-runner-workgc")
    # Assert
    assert "/.scitex/dev/logs/ci-runner-workgc.log" in spec.command


def test_ci_runner_workgc_description_non_empty():
    # Arrange
    # Act
    spec = _jobs.get_job("ci-runner-workgc")
    # Assert
    assert spec.description.strip() != ""


def test_list_jobs_includes_ci_runner_workgc():
    # Arrange
    # Act
    names = [s.name for s in _jobs.list_jobs()]
    # Assert
    assert "ci-runner-workgc" in names


# ---------------------------------------------------------------------------
# ecosystem-sync — schedules the WRITE self-pull (`scitex-dev ecosystem sync
# --yes`) so no editable checkout silently serves stale code. Motivated by the
# 2026-07-01 incidence where the workstation's own scitex-dev checkout was
# found 18 commits behind tag v0.21.0. Pins schedule / command / log path /
# rotation guard per the §3 "Adding a new job" checklist.
# ---------------------------------------------------------------------------


def test_registry_has_ecosystem_sync_entry():
    # Arrange
    # Act
    # Assert
    assert "ecosystem-sync" in _jobs.JOB_REGISTRY


def test_ecosystem_sync_name_matches_registry_key():
    # Arrange
    # Act
    spec = _jobs.get_job("ecosystem-sync")
    # Assert
    assert spec.name == "ecosystem-sync"


def test_ecosystem_sync_schedule_is_top_of_every_hour():
    # Arrange
    # Act
    spec = _jobs.get_job("ecosystem-sync")
    # Assert — hourly bounds drift to <=1h; cheap since ff-merge only runs
    # when a checkout is actually behind.
    assert spec.schedule == "0 * * * *"


def test_ecosystem_sync_command_invokes_ecosystem_sync_yes():
    # Arrange
    # Act
    spec = _jobs.get_job("ecosystem-sync")
    # Assert — must call the mutating self-pull, not the read-only preview.
    assert "scitex-dev ecosystem sync --yes" in spec.command


def test_ecosystem_sync_command_writes_to_named_log_file():
    # Arrange
    # Act
    spec = _jobs.get_job("ecosystem-sync")
    # Assert
    assert "/.scitex/dev/logs/cron-ecosystem-sync.log" in spec.command


def test_ecosystem_sync_command_keeps_one_mib_rotation_threshold():
    # Arrange
    # Act
    spec = _jobs.get_job("ecosystem-sync")
    # Assert — a sweep over ~60 repos writes a table each run, so the
    # 1-MiB rotate-to-.1 guard must be present.
    assert "1048576" in spec.command


def test_ecosystem_sync_description_mentions_ff_only_safety():
    # Arrange
    # Act
    spec = _jobs.get_job("ecosystem-sync")
    # Assert — `scitex-dev cron list` must make the never-clobber contract
    # obvious to operators without reading source.
    assert "ff-only" in spec.description


def test_list_jobs_includes_ecosystem_sync():
    # Arrange
    # Act
    names = [s.name for s in _jobs.list_jobs()]
    # Assert
    assert "ecosystem-sync" in names


# ---------------------------------------------------------------------------
# scholar-library-sync — one-way rsync of ~/.scitex/scholar/library from the
# host WSL (authority) to Spartan via `scitex-ssh sync` (sync_dir primitive,
# scitex-ssh>=1.1.0), then a remote derived-index rebuild. Design locked with
# scitex-scholar + scitex-ssh (card scholar-library-cross-machine-sync-
# 20260701). Pins schedule / command shape / safety invariants (no --delete,
# index.db* excluded, && short-circuit) per the §3 checklist.
# ---------------------------------------------------------------------------


def test_registry_has_scholar_library_sync_entry():
    # Arrange
    # Act
    # Assert
    assert "scholar-library-sync" in _jobs.JOB_REGISTRY


def test_scholar_library_sync_name_matches_registry_key():
    # Arrange
    # Act
    spec = _jobs.get_job("scholar-library-sync")
    # Assert
    assert spec.name == "scholar-library-sync"


def test_scholar_library_sync_schedule_is_every_six_hours_offset():
    # Arrange
    # Act
    spec = _jobs.get_job("scholar-library-sync")
    # Assert — :30 offset keeps it off the crowded 0-minute tick.
    assert spec.schedule == "30 */6 * * *"


def test_scholar_library_sync_command_pushes_library_to_spartan():
    # Arrange
    # Act
    spec = _jobs.get_job("scholar-library-sync")
    # Assert — one-way push: local library/ source, spartan: destination.
    assert (
        "scitex-ssh sync $HOME/.scitex/scholar/library/ "
        "spartan:.scitex/scholar/library/" in spec.command
    )


def test_scholar_library_sync_command_never_passes_delete():
    # Arrange
    # Act
    spec = _jobs.get_job("scholar-library-sync")
    # Assert — WSL is authority but a WSL-side pruning must never reap
    # Spartan copies; --delete is forbidden by design.
    assert "--delete" not in spec.command


def test_scholar_library_sync_command_excludes_all_index_db_siblings():
    # Arrange
    # Act
    spec = _jobs.get_job("scholar-library-sync")
    # Assert — the index is DERIVED state; shipping a live SQLite file
    # mid-write corrupts it. All four siblings must be excluded.
    missing = [
        name
        for name in (
            "index.db",
            "index.db-journal",
            "index.db-wal",
            "index.db-shm",
        )
        if f"--exclude {name}" not in spec.command
    ]
    assert missing == []


def test_scholar_library_sync_command_rebuilds_remote_index_after_push():
    # Arrange
    # Act
    spec = _jobs.get_job("scholar-library-sync")
    # Assert
    assert "scitex-scholar library db build" in spec.command


def test_scholar_library_sync_command_short_circuits_rebuild_on_rsync_failure():
    # Arrange
    spec = _jobs.get_job("scholar-library-sync")
    # Act — the rebuild must come after the sync joined by && so a partial
    # tree is never indexed.
    sync_pos = spec.command.index("scitex-ssh sync")
    rebuild_pos = spec.command.index("scitex-scholar library db build")
    joiner = spec.command[sync_pos:rebuild_pos]
    # Assert
    assert "&&" in joiner


def test_scholar_library_sync_command_precreates_remote_dir():
    # Arrange
    # Act
    spec = _jobs.get_job("scholar-library-sync")
    # Assert — mkdir -p over ssh instead of rsync --mkpath (Spartan's rsync
    # predates 3.2.3).
    assert "ssh spartan 'mkdir -p ~/.scitex/scholar/library'" in spec.command


def test_scholar_library_sync_command_runs_noninteractive():
    # Arrange
    # Act
    spec = _jobs.get_job("scholar-library-sync")
    # Assert — cron has no TTY; the CLI confirmation must be suppressed.
    assert "--yes" in spec.command


def test_scholar_library_sync_logs_under_scholar_runtime_dir():
    # Arrange
    # Act
    spec = _jobs.get_job("scholar-library-sync")
    # Assert — per the 2026-07-01 operator directive, the log lives under
    # the SCHOLAR leaf's user-level runtime dir, not ~/.scitex/dev/.
    assert "/.scitex/scholar/runtime/logs/cron-library-sync.log" in spec.command


def test_scholar_library_sync_command_keeps_one_mib_rotation_threshold():
    # Arrange
    # Act
    spec = _jobs.get_job("scholar-library-sync")
    # Assert
    assert "1048576" in spec.command


def test_scholar_library_sync_command_runs_dedupe_apply_before_sync():
    # Arrange
    spec = _jobs.get_job("scholar-library-sync")
    # Act — dedupe resolves duplicate-DOI dirs BEFORE they can sync to
    # Spartan or fail the remote build (scholar's sequencing requirement).
    dedupe_pos = spec.command.index(
        "scitex-scholar library dedupe --apply "
        "--library-root $HOME/.scitex/scholar/library"
    )
    sync_pos = spec.command.index("scitex-ssh sync")
    # Assert
    assert dedupe_pos < sync_pos


def test_scholar_library_sync_command_gates_sync_on_dedupe_success():
    # Arrange
    spec = _jobs.get_job("scholar-library-sync")
    # Act — && between dedupe and the rest: --apply exits non-zero ONLY on
    # unresolved conflicts or apply/IO error (contract pinned with
    # scholar), and that must block the push fail-loud.
    dedupe_pos = spec.command.index("library dedupe --apply")
    sync_pos = spec.command.index("scitex-ssh sync")
    joiner = spec.command[dedupe_pos:sync_pos]
    # Assert
    assert "&&" in joiner


def test_scholar_library_sync_command_never_hard_deletes():
    # Arrange
    # Act
    spec = _jobs.get_job("scholar-library-sync")
    # Assert — dedupe must stay quarantine-based (reversible); the
    # irreversible flag is forbidden in the unattended cron line.
    assert "--hard-delete" not in spec.command
