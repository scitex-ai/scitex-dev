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


def test_log_rotate_guard_embeds_threshold_and_target():
    # Arrange
    log = "$HOME/.scitex/dev/logs/example.log"
    # Act
    guard = _job_commands._log_rotate_guard(log)
    # Assert — must reference the 1-MiB threshold and rotate to <log>.1.
    assert str(_job_commands._LOG_ROTATE_BYTES) in guard and f"{log}.1" in guard


def test_log_rotate_guard_ends_with_composable_separator():
    # Arrange
    # Act
    guard = _job_commands._log_rotate_guard("$HOME/x.log")
    # Assert — documented contract: trailing "; " so it composes directly
    # in front of a command body.
    assert guard.endswith("; ")
