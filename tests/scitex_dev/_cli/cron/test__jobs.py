"""Unit tests pinning the cron job registry."""

from __future__ import annotations

import pytest

from scitex_dev._cli.cron import _job_commands, _jobs


def shell_body(name: str) -> str:
    """The job's PURE shell payload (no mkdir / redirect / rotation).

    Since the 2026-07-19 cron cleanup the crontab command is only
    ``scitex-dev cron exec <name>``; the payload of a shell-bodied job
    moved here, where `cron exec` runs it under the shared log sink.
    """
    return _job_commands.JOB_SHELL_BODIES[name]


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


def test_ci_watch_logs_under_dev_runtime_logs():
    # Arrange
    # Act — the log path is resolved by the verb now, not spelled into
    # the crontab line.
    log = _job_commands.log_path_for("ci-watch")
    # Assert — under runtime/, per the operator directive recorded in
    # jobs/_respawn.py:26. The pre-cleanup ~/.scitex/dev/logs/ violated it.
    assert log.as_posix().endswith(
        "/.scitex/dev/runtime/logs/cron-ci-watch.log"
    )


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


def test_worktree_gc_logs_under_dev_runtime_logs():
    # Arrange
    # Act
    log = _job_commands.log_path_for("worktree-gc")
    # Assert
    assert log.as_posix().endswith(
        "/.scitex/dev/runtime/logs/cron-worktree-gc.log"
    )


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


def test_task_harvest_logs_under_dev_runtime_logs():
    # Arrange
    # Act
    log = _job_commands.log_path_for("task-harvest")
    # Assert
    assert log.as_posix().endswith(
        "/.scitex/dev/runtime/logs/cron-task-harvest.log"
    )


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


def test_cred_distribute_logs_under_dev_runtime_logs():
    # Arrange
    # Act
    log = _job_commands.log_path_for("cred-distribute")
    # Assert
    assert log.as_posix().endswith(
        "/.scitex/dev/runtime/logs/cron-cred-distribute.log"
    )


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


def test_spartan_conn_monitor_logs_under_dev_runtime_logs():
    # Arrange
    # Act
    log = _job_commands.log_path_for("spartan-conn-monitor")
    # Assert
    assert log.as_posix().endswith(
        "/.scitex/dev/runtime/logs/cron-spartan-conn-monitor.log"
    )


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


def test_creds_rotate_all_body_invokes_creds_rotate_all_yes():
    # Arrange
    # Act — the payload moved out of the crontab into the shell body the
    # verb executes; the crontab line is now just `cron exec`.
    body = shell_body("creds-rotate-all")
    # Assert
    assert body == "scitex-dev creds rotate-all --yes"


def test_creds_rotate_all_logs_to_creds_rotate_slug_under_runtime():
    # Arrange
    # Act
    log = _job_commands.log_path_for("creds-rotate-all")
    # Assert — the slug stays `creds-rotate` (NO `cron-` prefix): the
    # ad-hoc line this entry retired used exactly that basename and
    # dashboards tailing it must keep working. Only the DIRECTORY moves,
    # from ~/.scitex/dev/logs/ to the mandated runtime/ layer.
    assert log.as_posix().endswith("/.scitex/dev/runtime/logs/creds-rotate.log")


def test_creds_rotate_all_body_carries_no_inline_plumbing():
    # Arrange
    # Act
    body = shell_body("creds-rotate-all")
    # Assert — the operator's complaint: mkdir / redirect / rotation
    # belong to the verb, not to the line. This job carried ALL THREE
    # inline; none may survive in the payload.
    assert "mkdir" not in body and ">>" not in body and "stat -c%s" not in body


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


def test_ci_runner_ensure_body_runs_the_host_script():
    # Arrange
    # Act
    body = shell_body("ci-runner-ensure")
    # Assert — $HOME, never ~: cron's /bin/sh -c does not reliably expand
    # a tilde (operator directive 2026-07-19).
    assert body == "$HOME/.scitex/dev/ci-runner-ensure-cron.sh"


def test_ci_runner_ensure_logs_under_dev_runtime_logs():
    # Arrange
    # Act
    log = _job_commands.log_path_for("ci-runner-ensure")
    # Assert
    assert log.as_posix().endswith(
        "/.scitex/dev/runtime/logs/ci-runner-ensure.log"
    )


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


def test_ci_runner_workgc_body_runs_the_host_script():
    # Arrange
    # Act
    body = shell_body("ci-runner-workgc")
    # Assert
    assert body == "$HOME/.scitex/dev/ci-runner-workgc-cron.sh"


def test_ci_runner_workgc_logs_under_dev_runtime_logs():
    # Arrange
    # Act
    log = _job_commands.log_path_for("ci-runner-workgc")
    # Assert
    assert log.as_posix().endswith(
        "/.scitex/dev/runtime/logs/ci-runner-workgc.log"
    )


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


def test_ecosystem_sync_body_invokes_ecosystem_sync_yes():
    # Arrange
    # Act
    body = shell_body("ecosystem-sync")
    # Assert — must call the mutating self-pull, not the read-only preview.
    assert body == "scitex-dev ecosystem sync --yes"


def test_ecosystem_sync_logs_under_dev_runtime_logs():
    # Arrange
    # Act
    log = _job_commands.log_path_for("ecosystem-sync")
    # Assert
    assert log.as_posix().endswith(
        "/.scitex/dev/runtime/logs/cron-ecosystem-sync.log"
    )


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
    body = shell_body("scholar-library-sync")
    # Assert — one-way push: local library/ source, spartan: destination.
    assert (
        "scitex-ssh sync $HOME/.scitex/scholar/library/ "
        "spartan:.scitex/scholar/library/" in body
    )


def test_scholar_library_sync_command_never_passes_delete():
    # Arrange
    # Act
    body = shell_body("scholar-library-sync")
    # Assert — WSL is authority but a WSL-side pruning must never reap
    # Spartan copies; --delete is forbidden by design.
    assert "--delete" not in body


def test_scholar_library_sync_command_excludes_all_index_db_siblings():
    # Arrange
    # Act
    body = shell_body("scholar-library-sync")
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
        if f"--exclude {name}" not in body
    ]
    assert missing == []


def test_scholar_library_sync_command_rebuilds_remote_index_after_push():
    # Arrange
    # Act
    body = shell_body("scholar-library-sync")
    # Assert
    assert "scitex-scholar library db build" in body


def test_scholar_library_sync_command_short_circuits_rebuild_on_rsync_failure():
    # Arrange
    body = shell_body("scholar-library-sync")
    # Act — the rebuild must come after the sync joined by && so a partial
    # tree is never indexed.
    sync_pos = body.index("scitex-ssh sync")
    rebuild_pos = body.index("scitex-scholar library db build")
    joiner = body[sync_pos:rebuild_pos]
    # Assert
    assert "&&" in joiner


def test_scholar_library_sync_command_precreates_remote_dir():
    # Arrange
    # Act
    body = shell_body("scholar-library-sync")
    # Assert — mkdir -p over ssh instead of rsync --mkpath (Spartan's rsync
    # predates 3.2.3).
    # $HOME rather than ~ per the 2026-07-19 directive; inside the single
    # quotes it reaches the REMOTE shell literally and expands there.
    assert "ssh spartan 'mkdir -p $HOME/.scitex/scholar/library'" in body


def test_scholar_library_sync_command_runs_noninteractive():
    # Arrange
    # Act
    body = shell_body("scholar-library-sync")
    # Assert — cron has no TTY; the CLI confirmation must be suppressed.
    assert "--yes" in body


def test_scholar_library_sync_logs_under_scholar_runtime_dir():
    # Arrange
    # Act
    log = _job_commands.log_path_for("scholar-library-sync")
    # Assert — per the 2026-07-01 operator directive, the log lives under
    # the SCHOLAR leaf's user-level runtime dir, not ~/.scitex/dev/: the
    # data being synced is scholar state, so its log lives with it.
    assert log.as_posix().endswith(
        "/.scitex/scholar/runtime/logs/cron-library-sync.log"
    )


def test_scholar_library_sync_command_runs_dedupe_apply_before_sync():
    # Arrange
    body = shell_body("scholar-library-sync")
    # Act — dedupe resolves duplicate-DOI dirs BEFORE they can sync to
    # Spartan or fail the remote build (scholar's sequencing requirement).
    dedupe_pos = body.index(
        "scitex-scholar library dedupe --apply "
        "--library-root $HOME/.scitex/scholar/library"
    )
    sync_pos = body.index("scitex-ssh sync")
    # Assert
    assert dedupe_pos < sync_pos


def test_scholar_library_sync_command_gates_sync_on_dedupe_success():
    # Arrange
    body = shell_body("scholar-library-sync")
    # Act — && between dedupe and the rest: --apply exits non-zero ONLY on
    # unresolved conflicts or apply/IO error (contract pinned with
    # scholar), and that must block the push fail-loud.
    dedupe_pos = body.index("library dedupe --apply")
    sync_pos = body.index("scitex-ssh sync")
    joiner = body[dedupe_pos:sync_pos]
    # Assert
    assert "&&" in joiner


def test_scholar_library_sync_command_never_hard_deletes():
    # Arrange
    # Act
    body = shell_body("scholar-library-sync")
    # Assert — dedupe must stay quarantine-based (reversible); the
    # irreversible flag is forbidden in the unattended cron line.
    assert "--hard-delete" not in body


# ---------------------------------------------------------------------------
# Registry-wide invariants for the 2026-07-19 cron cleanup. These are the
# operator's three asks, pinned once for EVERY job rather than job-by-job:
#   1. mkdir / redirect / rotation belong to the cron verb, not the line.
#   2. generated shell text uses $HOME, never ~.
#   3. the crontab is not to be noisy.
# ---------------------------------------------------------------------------


def test_every_crontab_command_is_exactly_cron_exec_name():
    # Arrange
    # Act
    offenders = {
        spec.name: spec.command
        for spec in _jobs.list_jobs()
        if spec.command != f"scitex-dev cron exec {spec.name}"
    }
    # Assert — schedule + command + marker is the WHOLE line.
    assert offenders == {}


def test_no_crontab_command_carries_shell_plumbing():
    # Arrange
    # Act — mkdir, redirect, rotation, and command chaining are exactly
    # the noise the operator objected to ("cron が汚すぎる").
    noise = ("mkdir", ">>", "2>&1", "stat -c%s", ";", "&&", "$(dirname")
    offenders = {
        spec.name: [tok for tok in noise if tok in spec.command]
        for spec in _jobs.list_jobs()
        if any(tok in spec.command for tok in noise)
    }
    # Assert
    assert offenders == {}


def test_no_generated_shell_text_uses_bare_tilde_home():
    # Arrange — ~ is expanded only by an interactive shell in command
    # position; cron's /bin/sh -c context and $(dirname ~/...) do NOT
    # reliably expand it, so generated text must use $HOME.
    generated = [spec.command for spec in _jobs.list_jobs()]
    generated += list(_job_commands.JOB_SHELL_BODIES.values())
    # Act
    offenders = [text for text in generated if "~/" in text]
    # Assert
    assert offenders == []


def test_every_job_logs_under_a_runtime_logs_directory():
    # Arrange
    # Act — runtime/ is the documented regenerable-state layer,
    # redirectable off GPFS for inode safety; job logs are exactly the
    # high-cardinality regenerable writes it exists for.
    offenders = {
        spec.name: _job_commands.log_path_for(spec.name).as_posix()
        for spec in _jobs.list_jobs()
        if "/runtime/logs/" not in _job_commands.log_path_for(spec.name).as_posix()
    }
    # Assert
    assert offenders == {}


def test_no_job_logs_under_the_forbidden_dev_logs_directory():
    # Arrange
    # Act — the specific directive being violated before this cleanup
    # (jobs/_respawn.py:25-27): never ~/.scitex/<pkg>/logs/.
    offenders = {
        spec.name: _job_commands.log_path_for(spec.name).as_posix()
        for spec in _jobs.list_jobs()
        if "/.scitex/dev/logs/" in _job_commands.log_path_for(spec.name).as_posix()
    }
    # Assert
    assert offenders == {}


def test_every_registered_job_has_a_body_or_a_shell_payload():
    # Arrange — a registry entry with neither a dispatch branch nor a
    # shell payload would fail at cron time, not at test time.
    from scitex_dev._cli.cron import run as run_mod

    python_bodied = {
        "ci-watch",
        "quota-keepalive",
        "worktree-gc",
        "task-harvest",
        "cred-distribute",
        "spartan-conn-monitor",
    }
    # Act
    orphans = [
        name
        for name in _jobs.JOB_REGISTRY
        if name not in python_bodied
        and name not in _job_commands.JOB_SHELL_BODIES
    ]
    # Assert
    assert orphans == [] and run_mod is not None


def test_shell_payloads_carry_no_inline_plumbing():
    # Arrange
    # Act — the payloads are PURE; `cron exec` supplies mkdir, redirect
    # and rotation for all of them uniformly.
    offenders = {
        name: body
        for name, body in _job_commands.JOB_SHELL_BODIES.items()
        if "mkdir -p $(dirname" in body or ">>" in body or "stat -c%s" in body
    }
    # Assert
    assert offenders == {}
