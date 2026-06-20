"""Unit tests for scitex_dev._cli.cron._worktree_gc.

No mocks (PA-306 / STX-NM*). The body is exercised against real
``tmp_path`` directories on disk; the ``git`` invocation is passed as a
real callable seam so the production code runs its full path / parse /
gate / removal logic.

The single highest-stakes invariant — never touching paths outside
``.claude/worktrees`` — is pinned by multiple direct unit tests on
:func:`_is_managed_path` AND by an end-to-end test that hands the body
a fake ``git`` runner returning paths that include a ``.worktrees/``
trap and asserts the trap is never removed.
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest

from scitex_dev._cli.cron import _jobs, _worktree_gc


# ---------------------------------------------------------------------------
# _is_managed_path — the highest-stakes guardrail. Every change to this
# function must keep these tests green, no exceptions.
# ---------------------------------------------------------------------------


def test_is_managed_path_accepts_claude_worktrees():
    # Arrange
    p = "/home/u/proj/myrepo/.claude/worktrees/agent-1"
    # Act
    result = _worktree_gc._is_managed_path(p)
    # Assert
    assert result is True


def test_is_managed_path_rejects_bare_worktrees():
    # Arrange — the operator's own worktrees dir (no .claude prefix).
    p = "/home/u/proj/myrepo/.worktrees/feature-x"
    # Act
    result = _worktree_gc._is_managed_path(p)
    # Assert
    assert result is False


def test_is_managed_path_rejects_random_path():
    # Arrange
    p = "/home/u/proj/myrepo/src/main.py"
    # Act
    result = _worktree_gc._is_managed_path(p)
    # Assert
    assert result is False


def test_is_managed_path_rejects_substring_lookalike():
    # Arrange — a directory literally named ``foo.claude.worktrees``
    # must not be mistaken for the managed segment. The substring check
    # requires a leading slash on ``.claude/worktrees/``.
    p = "/home/u/foo.claude.worktrees/agent-1"
    # Act
    result = _worktree_gc._is_managed_path(p)
    # Assert
    assert result is False


# ---------------------------------------------------------------------------
# _list_registered_worktrees — filters git's porcelain output through the
# guardrail.
# ---------------------------------------------------------------------------


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _ScriptedGitRunner:
    """A real callable that returns a canned answer per argv pattern.

    Tests register ``(matcher, completed)`` pairs; the matcher is called
    with the argv list and returns bool. The first matcher to fire wins.
    Argv calls that match no pattern record into ``self.misses`` and
    return rc=1 — so a test asserting "git worktree remove was NEVER
    called for path X" can also check ``calls`` directly.
    """

    def __init__(self):
        self.scripts: list[tuple[callable, _FakeCompleted]] = []
        self.calls: list[list[str]] = []
        self.misses: list[list[str]] = []

    def when(self, matcher, completed: _FakeCompleted):
        self.scripts.append((matcher, completed))
        return self

    def __call__(self, argv: list[str]) -> _FakeCompleted:
        self.calls.append(list(argv))
        for matcher, completed in self.scripts:
            if matcher(argv):
                return completed
        self.misses.append(list(argv))
        return _FakeCompleted(returncode=1, stderr="no scripted answer")


# Shared helper — builds the standard "managed + protected" porcelain
# string. Tests assemble specifics around it; the helper keeps the
# multi-worktree fixture out of every test body so each test stays
# single-assertion (STX-TQ007).
_PORCELAIN_HEADER = (
    "worktree /home/u/proj/myrepo\n"
    "HEAD abc\n"
    "branch refs/heads/develop\n"
    "\n"
    "worktree /home/u/proj/myrepo/.claude/worktrees/agent-1\n"
    "HEAD def\n"
    "branch refs/heads/feat/x\n"
    "\n"
    "worktree /home/u/proj/myrepo/.worktrees/operator-x\n"
    "HEAD ghi\n"
    "branch refs/heads/operator-x\n"
)


def test_list_registered_worktrees_yields_the_managed_segment_path():
    # Arrange
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-3:] == ["worktree", "list", "--porcelain"],
        _FakeCompleted(returncode=0, stdout=_PORCELAIN_HEADER),
    )
    # Act
    out = _worktree_gc._list_registered_worktrees("/home/u/proj/myrepo", runner)
    # Assert
    assert out == ["/home/u/proj/myrepo/.claude/worktrees/agent-1"]


def test_list_registered_worktrees_returns_empty_on_git_failure():
    # Arrange
    runner = _ScriptedGitRunner().when(
        lambda argv: True,
        _FakeCompleted(returncode=1, stderr="not a git repo"),
    )
    # Act
    out = _worktree_gc._list_registered_worktrees("/some/path", runner)
    # Assert
    assert out == []


# ---------------------------------------------------------------------------
# _gc_one_worktree — the per-worktree decision: gate by guardrail, by
# mtime, then call git worktree remove. Tests split one-assert-per-body
# to satisfy STX-TQ007; a shared helper builds the boilerplate so each
# body stays small.
# ---------------------------------------------------------------------------


def _gc_call_outside_segment(tmp_path):
    """Set up a `_gc_one_worktree` call against a NON-managed path so the
    per-worktree boundary guardrail kicks in. Returns (outcome, runner)
    so the caller can assert on either the outcome OR the runner state
    independently (STX-TQ007: one assert per test)."""
    bad = tmp_path / "regular-dir"
    bad.mkdir()
    runner = _ScriptedGitRunner()
    out = _worktree_gc._gc_one_worktree(
        repo=str(tmp_path),
        path=str(bad),
        now_epoch=time.time(),
        max_age_seconds=0.0,
        git_runner=runner,
        dry_run=False,
    )
    return out, runner


def test_gc_one_worktree_outside_segment_action_is_errored(tmp_path):
    # Arrange
    # Act
    out, _ = _gc_call_outside_segment(tmp_path)
    # Assert
    assert out.action == "errored"


def test_gc_one_worktree_outside_segment_detail_names_guardrail(tmp_path):
    # Arrange
    # Act
    out, _ = _gc_call_outside_segment(tmp_path)
    # Assert
    assert "guardrail" in out.detail


def test_gc_one_worktree_outside_segment_never_calls_git(tmp_path):
    # Arrange
    # Act
    _, runner = _gc_call_outside_segment(tmp_path)
    # Assert — the per-worktree boundary refused before any git call.
    assert runner.calls == []


def _gc_call_fresh(tmp_path):
    """A managed worktree whose mtime is "right now" → skipped-fresh."""
    repo = tmp_path / "proj" / "myrepo"
    wt = repo / ".claude" / "worktrees" / "agent-fresh"
    wt.mkdir(parents=True)
    runner = _ScriptedGitRunner()
    out = _worktree_gc._gc_one_worktree(
        repo=str(repo),
        path=str(wt),
        now_epoch=time.time(),
        max_age_seconds=86400.0,
        git_runner=runner,
        dry_run=False,
    )
    return out, runner


def test_gc_one_worktree_fresh_action_is_skipped_fresh(tmp_path):
    # Arrange
    # Act
    out, _ = _gc_call_fresh(tmp_path)
    # Assert
    assert out.action == "skipped-fresh"


def test_gc_one_worktree_fresh_never_calls_git(tmp_path):
    # Arrange
    # Act
    _, runner = _gc_call_fresh(tmp_path)
    # Assert
    assert runner.calls == []


def _gc_call_stale(tmp_path):
    """A managed worktree backdated 10 days → removed (mtime > threshold)."""
    repo = tmp_path / "proj" / "myrepo"
    wt = repo / ".claude" / "worktrees" / "agent-stale"
    wt.mkdir(parents=True)
    old = time.time() - 10 * 86400
    os.utime(wt, (old, old))
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-3:-1] == ["worktree", "remove"],
        _FakeCompleted(returncode=0, stdout="removed"),
    )
    out = _worktree_gc._gc_one_worktree(
        repo=str(repo),
        path=str(wt),
        now_epoch=time.time(),
        max_age_seconds=86400.0,
        git_runner=runner,
        dry_run=False,
    )
    return out, runner


def test_gc_one_worktree_stale_action_is_removed(tmp_path):
    # Arrange
    # Act
    out, _ = _gc_call_stale(tmp_path)
    # Assert
    assert out.action == "removed"


def test_gc_one_worktree_stale_invokes_git_worktree_remove(tmp_path):
    # Arrange
    # Act
    _, runner = _gc_call_stale(tmp_path)
    saw_remove = any(
        argv[-2:] == ["worktree", "remove"] or argv[-3:-1] == ["worktree", "remove"]
        for argv in runner.calls
    )
    # Assert
    assert saw_remove is True


def _gc_call_dry_run(tmp_path):
    """A stale managed worktree with dry_run=True → reports `removed` but
    never invokes git."""
    repo = tmp_path / "proj" / "myrepo"
    wt = repo / ".claude" / "worktrees" / "agent-dry"
    wt.mkdir(parents=True)
    old = time.time() - 10 * 86400
    os.utime(wt, (old, old))
    runner = _ScriptedGitRunner()
    out = _worktree_gc._gc_one_worktree(
        repo=str(repo),
        path=str(wt),
        now_epoch=time.time(),
        max_age_seconds=86400.0,
        git_runner=runner,
        dry_run=True,
    )
    return out, runner


def test_gc_one_worktree_dry_run_action_is_removed(tmp_path):
    # Arrange
    # Act
    out, _ = _gc_call_dry_run(tmp_path)
    # Assert
    assert out.action == "removed"


def test_gc_one_worktree_dry_run_detail_says_dry_run(tmp_path):
    # Arrange
    # Act
    out, _ = _gc_call_dry_run(tmp_path)
    # Assert
    assert "dry-run" in out.detail


def test_gc_one_worktree_dry_run_never_calls_git(tmp_path):
    # Arrange
    # Act
    _, runner = _gc_call_dry_run(tmp_path)
    # Assert
    assert runner.calls == []


def _gc_call_git_refusal(tmp_path):
    """A stale managed worktree where git refuses (dirty / locked)."""
    repo = tmp_path / "proj" / "myrepo"
    wt = repo / ".claude" / "worktrees" / "agent-dirty"
    wt.mkdir(parents=True)
    old = time.time() - 10 * 86400
    os.utime(wt, (old, old))
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-3:-1] == ["worktree", "remove"],
        _FakeCompleted(returncode=1, stderr="fatal: working tree is dirty"),
    )
    out = _worktree_gc._gc_one_worktree(
        repo=str(repo),
        path=str(wt),
        now_epoch=time.time(),
        max_age_seconds=86400.0,
        git_runner=runner,
        dry_run=False,
    )
    return out, wt


def test_gc_one_worktree_git_refusal_action_is_skipped_refused(tmp_path):
    # Arrange
    # Act
    out, _ = _gc_call_git_refusal(tmp_path)
    # Assert
    assert out.action == "skipped-refused"


def test_gc_one_worktree_git_refusal_detail_carries_git_message(tmp_path):
    # Arrange
    # Act
    out, _ = _gc_call_git_refusal(tmp_path)
    # Assert
    assert "dirty" in out.detail


def test_gc_one_worktree_git_refusal_leaves_directory_intact(tmp_path):
    # Arrange
    # Act
    _, wt = _gc_call_git_refusal(tmp_path)
    # Assert — never force-removed.
    assert wt.exists()


# ---------------------------------------------------------------------------
# run_once — end-to-end smoke. The hardest invariant: when a repo has
# both a `.claude/worktrees/<managed>` AND a `.worktrees/<protected>`
# entry registered, `git worktree remove` is NEVER called for the
# protected one.
# ---------------------------------------------------------------------------


def _run_once_managed_and_protected(tmp_path):
    """Build the end-to-end fixture with BOTH a managed and a protected
    stale worktree registered; return (result, runner, managed_path,
    protected_path) so each test can assert one property."""
    repo = tmp_path / "proj" / "myrepo"
    repo.mkdir(parents=True)
    managed = repo / ".claude" / "worktrees" / "agent-stale"
    managed.mkdir(parents=True)
    protected = repo / ".worktrees" / "operator-x"
    protected.mkdir(parents=True)
    old = time.time() - 10 * 86400
    os.utime(managed, (old, old))
    os.utime(protected, (old, old))

    porcelain = f"worktree {repo}\n\nworktree {managed}\n\nworktree {protected}\n"
    runner = (
        _ScriptedGitRunner()
        .when(
            lambda argv: argv[-3:] == ["worktree", "list", "--porcelain"],
            _FakeCompleted(returncode=0, stdout=porcelain),
        )
        .when(
            lambda argv: argv[-2:-1] == ["remove"],
            _FakeCompleted(returncode=0),
        )
        .when(
            lambda argv: argv[-1] == "prune",
            _FakeCompleted(returncode=0),
        )
    )
    out_buf = io.StringIO()
    result = _worktree_gc.run_once(
        roots=[str(tmp_path)],
        max_age_days=1.0,
        git_runner=runner,
        out=out_buf,
    )
    return result, runner, managed, protected


def test_run_once_protected_never_in_remove_calls(tmp_path):
    # Arrange
    # Act
    _, runner, _, protected = _run_once_managed_and_protected(tmp_path)
    remove_calls = [
        argv for argv in runner.calls if "remove" in argv and "worktree" in argv
    ]
    protected_seen = any(str(protected) in argv for argv in remove_calls)
    # Assert — this is the single highest-stakes invariant of this PR.
    assert protected_seen is False


def test_run_once_managed_is_removed(tmp_path):
    # Arrange
    # Act
    result, _, _, _ = _run_once_managed_and_protected(tmp_path)
    # Assert
    assert result.removed == 1


def test_run_once_protected_not_scanned(tmp_path):
    # Arrange
    # Act
    result, _, _, _ = _run_once_managed_and_protected(tmp_path)
    # Assert — protected was filtered out before per_worktree even runs.
    assert result.scanned == 1


def test_run_once_remove_call_targets_the_managed_path(tmp_path):
    # Arrange
    # Act
    _, runner, managed, _ = _run_once_managed_and_protected(tmp_path)
    remove_calls = [
        argv for argv in runner.calls if "remove" in argv and "worktree" in argv
    ]
    # Assert
    assert any(str(managed) in argv for argv in remove_calls)


def _run_once_no_roots(tmp_path):
    """Point run_once at a non-existent root → error path."""
    out_buf = io.StringIO()
    result = _worktree_gc.run_once(
        roots=[str(tmp_path / "does-not-exist")],
        max_age_days=1.0,
        git_runner=_ScriptedGitRunner(),
        out=out_buf,
    )
    return result


def test_run_once_no_roots_records_error(tmp_path):
    # Arrange
    # Act
    result = _run_once_no_roots(tmp_path)
    # Assert
    assert result.error is not None


def test_run_once_no_roots_error_names_search_roots(tmp_path):
    # Arrange
    # Act
    result = _run_once_no_roots(tmp_path)
    # Assert
    assert "no usable search roots" in result.error


def test_run_once_no_roots_scanned_is_zero(tmp_path):
    # Arrange
    # Act
    result = _run_once_no_roots(tmp_path)
    # Assert
    assert result.scanned == 0


def _run_once_env_threshold_keeps_5day_fresh(tmp_path):
    """Set ``SCITEX_WORKTREE_GC_MAX_AGE_DAYS=30`` via direct os.environ
    mutation (PA-306 forbids monkeypatch), wrap in try/finally for
    cleanup, return the result."""
    repo = tmp_path / "proj" / "myrepo"
    managed = repo / ".claude" / "worktrees" / "agent-mediumage"
    managed.mkdir(parents=True)
    old = time.time() - 5 * 86400
    os.utime(managed, (old, old))
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-3:] == ["worktree", "list", "--porcelain"],
        _FakeCompleted(returncode=0, stdout=f"worktree {managed}\n"),
    )

    env_key = "SCITEX_WORKTREE_GC_MAX_AGE_DAYS"
    prev = os.environ.get(env_key)
    os.environ[env_key] = "30"
    try:
        out_buf = io.StringIO()
        result = _worktree_gc.run_once(
            roots=[str(tmp_path)],
            git_runner=runner,
            out=out_buf,
        )
    finally:
        if prev is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = prev
    return result


def test_run_once_env_threshold_30d_no_removal_of_5day_old(tmp_path):
    # Arrange
    # Act
    result = _run_once_env_threshold_keeps_5day_fresh(tmp_path)
    # Assert
    assert result.removed == 0


def test_run_once_env_threshold_30d_skipped_fresh_recorded(tmp_path):
    # Arrange
    # Act
    result = _run_once_env_threshold_keeps_5day_fresh(tmp_path)
    # Assert
    assert result.skipped_fresh == 1


# ---------------------------------------------------------------------------
# Container-worktree protection (lead-learnings/19, 2026-06-13)
#
# A bare ``git worktree prune`` from the host CHECKOUT destroys live
# container worktrees because their recorded gitdir (``/work/<...>/.git``)
# is unresolvable from outside the container — git treats "directory
# missing" as "dangling" and prunes. ``_safe_prune`` walks the repo's
# ``.git/worktrees/*/gitdir`` registry and, if ANY entry points at
# ``/work/`` (the agent-container bind-mount root), skips the prune
# wholesale rather than risk wiping out integration-test work.
# ---------------------------------------------------------------------------


def _make_main_repo_with_worktree_registry(tmp_path, gitdir_targets):
    """Build a fake main-repo layout with one .git/worktrees/<n>/gitdir
    per entry in ``gitdir_targets`` (each entry is the recorded path).

    Returns the main-repo dir. No real ``git init`` needed — the prune
    helper only reads the registry's ``gitdir`` files; the rest of git's
    machinery never sees these paths.
    """
    repo = tmp_path / "main-repo"
    (repo / ".git" / "worktrees").mkdir(parents=True)
    for i, target in enumerate(gitdir_targets):
        entry = repo / ".git" / "worktrees" / f"wt{i}"
        entry.mkdir()
        (entry / "gitdir").write_text(target + "\n")
    return repo


def test_gitdir_targets_container_recognises_work_prefix(tmp_path):
    # Arrange
    gitdir_file = tmp_path / "gitdir"
    gitdir_file.write_text("/work/.worktrees/foo/.git\n")
    # Act
    result = _worktree_gc._gitdir_targets_container(gitdir_file)
    # Assert
    assert result is True


def test_gitdir_targets_container_rejects_host_path(tmp_path):
    # Arrange — a normal host worktree's gitdir lives under the user home.
    gitdir_file = tmp_path / "gitdir"
    gitdir_file.write_text("/home/u/proj/myrepo/.claude/worktrees/agent-1/.git\n")
    # Act
    result = _worktree_gc._gitdir_targets_container(gitdir_file)
    # Assert
    assert result is False


def test_gitdir_targets_container_handles_missing_file(tmp_path):
    # Arrange — registry entry whose ``gitdir`` file has been removed
    # (race window between mkdir and write). Must NOT crash.
    missing = tmp_path / "nonexistent-gitdir"
    # Act
    result = _worktree_gc._gitdir_targets_container(missing)
    # Assert
    assert result is False


def test_has_container_worktree_true_when_work_entry_present(tmp_path):
    # Arrange
    repo = _make_main_repo_with_worktree_registry(
        tmp_path,
        ["/work/.worktrees/m4-integration/.git"],
    )
    # Act
    result = _worktree_gc._has_container_worktree(str(repo))
    # Assert
    assert result is True


def test_has_container_worktree_false_when_only_host_entries(tmp_path):
    # Arrange
    repo = _make_main_repo_with_worktree_registry(
        tmp_path,
        [
            "/home/u/proj/myrepo/.claude/worktrees/agent-1/.git",
            "/home/u/proj/myrepo/.claude/worktrees/agent-2/.git",
        ],
    )
    # Act
    result = _worktree_gc._has_container_worktree(str(repo))
    # Assert
    assert result is False


def test_has_container_worktree_false_when_registry_absent(tmp_path):
    # Arrange — repo with no `.git/worktrees/` at all.
    repo = tmp_path / "main-repo"
    (repo / ".git").mkdir(parents=True)
    # Act
    result = _worktree_gc._has_container_worktree(str(repo))
    # Assert
    assert result is False


def test_safe_prune_skips_when_container_worktree_present_returns_false(tmp_path):
    # Arrange — registry contains a live container worktree.
    repo = _make_main_repo_with_worktree_registry(
        tmp_path,
        ["/work/.worktrees/m4-integration/.git"],
    )
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-1] == "prune",
        _FakeCompleted(returncode=0),
    )
    # Act
    invoked = _worktree_gc._safe_prune(str(repo), runner, out=io.StringIO())
    # Assert
    assert invoked is False


def test_safe_prune_skips_when_container_worktree_present_runner_not_called(tmp_path):
    # Arrange — regression sentinel: even ONE container worktree in the
    # registry must keep the runner away from ``worktree prune``.
    repo = _make_main_repo_with_worktree_registry(
        tmp_path,
        [
            "/home/u/proj/myrepo/.claude/worktrees/agent-1/.git",
            "/work/.worktrees/m4-integration/.git",
        ],
    )
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-1] == "prune",
        _FakeCompleted(returncode=0),
    )
    # Act
    _worktree_gc._safe_prune(str(repo), runner, out=io.StringIO())
    # Assert
    assert all("prune" not in argv for argv in runner.calls)


def test_safe_prune_invokes_prune_when_no_container_worktree_returns_true(tmp_path):
    # Arrange — host-only registry; prune is safe.
    repo = _make_main_repo_with_worktree_registry(
        tmp_path,
        ["/home/u/proj/myrepo/.claude/worktrees/agent-1/.git"],
    )
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-1] == "prune",
        _FakeCompleted(returncode=0),
    )
    # Act
    invoked = _worktree_gc._safe_prune(str(repo), runner, out=io.StringIO())
    # Assert
    assert invoked is True


def test_safe_prune_invokes_prune_when_no_container_worktree_runner_called(tmp_path):
    # Arrange — paired sentinel: confirm the runner was actually called
    # with ``worktree prune`` (not just that the helper returned True).
    repo = _make_main_repo_with_worktree_registry(
        tmp_path,
        ["/home/u/proj/myrepo/.claude/worktrees/agent-1/.git"],
    )
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-1] == "prune",
        _FakeCompleted(returncode=0),
    )
    # Act
    _worktree_gc._safe_prune(str(repo), runner, out=io.StringIO())
    # Assert
    assert any("prune" in argv for argv in runner.calls)


def test_safe_prune_skip_log_mentions_lead_learnings(tmp_path):
    # Arrange — the skip log must point a reader at the documented
    # incident so they understand WHY this prune was suppressed.
    repo = _make_main_repo_with_worktree_registry(
        tmp_path,
        ["/work/.worktrees/m4-integration/.git"],
    )
    runner = _ScriptedGitRunner()
    out_buf = io.StringIO()
    # Act
    _worktree_gc._safe_prune(str(repo), runner, out=out_buf)
    # Assert
    assert "lead-learnings/19" in out_buf.getvalue()


# EOF
