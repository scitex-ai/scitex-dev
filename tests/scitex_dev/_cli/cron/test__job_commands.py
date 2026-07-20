"""Tests for the extracted per-job shell-line builders (``_job_commands``).

The builders moved VERBATIM out of ``_jobs.py`` (512-line cap refactor);
their behaviour is pinned job-by-job in ``test__jobs.py`` through the
registry. These tests pin the EXTRACTION contract itself: the module is
importable, ``_jobs`` re-exports every builder under its original name,
and the shared rotation guard composes as documented.
"""

from __future__ import annotations

from scitex_dev._cli.cron import _job_commands, _jobs

_BUILDER_NAMES = (
    "_ci_runner_ensure_command",
    "_ci_runner_workgc_command",
    "_ci_watch_command",
    "_cred_distribute_command",
    "_creds_rotate_all_command",
    "_ecosystem_sync_command",
    "_quota_keepalive_command",
    "_scholar_library_sync_command",
    "_spartan_conn_monitor_command",
    "_task_harvest_command",
    "_worktree_gc_command",
)


def test_jobs_module_reexports_every_builder():
    # Arrange
    # Act — the re-export keeps `_jobs._ecosystem_sync_command`-style
    # imports (callers + older tests) resolving after the extraction.
    missing = [n for n in _BUILDER_NAMES if not hasattr(_jobs, n)]
    # Assert
    assert missing == []


def test_reexported_builders_are_the_same_objects():
    # Arrange
    # Act
    diverged = [
        n
        for n in _BUILDER_NAMES
        if getattr(_jobs, n) is not getattr(_job_commands, n)
    ]
    # Assert — identity, not equality: _jobs must not shadow with copies.
    assert diverged == []


def test_every_builder_returns_nonempty_shell_line():
    # Arrange
    # Act
    empty = [
        n for n in _BUILDER_NAMES if not getattr(_job_commands, n)().strip()
    ]
    # Assert
    assert empty == []


def test_no_builder_emits_an_inline_log_rotation_guard():
    # Arrange — the 1-MiB guard used to be spliced into the crontab line
    # by `_log_rotate_guard`. It now lives in the shared log sink
    # (`jobs._logsink.rotate_if_large`), which applies it to EVERY job
    # rather than the two lines that happened to carry it.
    # Act
    offenders = [
        n
        for n in _BUILDER_NAMES
        if "stat -c%s" in getattr(_job_commands, n)()
    ]
    # Assert
    assert offenders == []


def test_builders_no_longer_expose_the_retired_rotation_guard():
    # Arrange
    # Act
    # Assert — leaving a dead helper around invites re-inlining it.
    assert not hasattr(_job_commands, "_log_rotate_guard")


def test_every_builder_emits_only_the_cron_exec_invocation():
    # Arrange — the operator's ask: the line carries schedule + command,
    # with all plumbing owned by the verb.
    # Act
    offenders = [
        n
        for n in _BUILDER_NAMES
        if not getattr(_job_commands, n)().startswith("scitex-dev cron exec ")
    ]
    # Assert
    assert offenders == []
