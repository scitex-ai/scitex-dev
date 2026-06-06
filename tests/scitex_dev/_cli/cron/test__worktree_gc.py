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
    # Act / Assert
    assert _worktree_gc._is_managed_path(p) is True


def test_is_managed_path_rejects_bare_worktrees():
    # Arrange — the operator's own worktrees dir (no .claude prefix).
    p = "/home/u/proj/myrepo/.worktrees/feature-x"
    # Act / Assert
    assert _worktree_gc._is_managed_path(p) is False


def test_is_managed_path_rejects_random_path():
    # Arrange
    p = "/home/u/proj/myrepo/src/main.py"
    # Act / Assert
    assert _worktree_gc._is_managed_path(p) is False


def test_is_managed_path_rejects_substring_lookalike():
    # Arrange — a directory literally named ``foo.claude.worktrees`` must
    # not be mistaken for the managed segment. The substring check
    # requires a leading slash on ``.claude/worktrees/``.
    p = "/home/u/foo.claude.worktrees/agent-1"
    # Act / Assert
    assert _worktree_gc._is_managed_path(p) is False


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


def test_list_registered_worktrees_filters_to_managed_segment():
    # Arrange — fake porcelain output with one managed worktree, one
    # protected, one totally unrelated.
    porcelain = (
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
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-3:] == ["worktree", "list", "--porcelain"],
        _FakeCompleted(returncode=0, stdout=porcelain),
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
# mtime, then call git worktree remove.
# ---------------------------------------------------------------------------


def test_gc_one_worktree_refuses_path_outside_managed_segment(tmp_path):
    # Arrange — even if the caller bypassed the list filter, the per-
    # worktree boundary re-checks the guardrail. This is defence in
    # depth and the test must keep that property pinned.
    bad = tmp_path / "regular-dir"
    bad.mkdir()
    runner = _ScriptedGitRunner()
    # Act
    out = _worktree_gc._gc_one_worktree(
        repo=str(tmp_path),
        path=str(bad),
        now_epoch=time.time(),
        max_age_seconds=0.0,
        git_runner=runner,
        dry_run=False,
    )
    # Assert
    assert out.action == "errored"
    assert "guardrail" in out.detail
    # And critically: git was never called.
    assert runner.calls == []


def test_gc_one_worktree_skips_fresh(tmp_path):
    # Arrange — build a path with the managed segment in it.
    repo = tmp_path / "proj" / "myrepo"
    wt = repo / ".claude" / "worktrees" / "agent-fresh"
    wt.mkdir(parents=True)
    runner = _ScriptedGitRunner()
    # Act — mtime is "right now", threshold 1 day → fresh.
    out = _worktree_gc._gc_one_worktree(
        repo=str(repo),
        path=str(wt),
        now_epoch=time.time(),
        max_age_seconds=86400.0,
        git_runner=runner,
        dry_run=False,
    )
    # Assert
    assert out.action == "skipped-fresh"
    assert runner.calls == []


def test_gc_one_worktree_removes_stale(tmp_path):
    # Arrange
    repo = tmp_path / "proj" / "myrepo"
    wt = repo / ".claude" / "worktrees" / "agent-stale"
    wt.mkdir(parents=True)
    # Backdate mtime to 10 days ago — well past the default 3-day
    # threshold, comfortable margin against clock jitter.
    old = time.time() - 10 * 86400
    os.utime(wt, (old, old))
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-3:-1] == ["worktree", "remove"],
        _FakeCompleted(returncode=0, stdout="removed"),
    )
    # Act
    out = _worktree_gc._gc_one_worktree(
        repo=str(repo),
        path=str(wt),
        now_epoch=time.time(),
        max_age_seconds=86400.0,  # 1-day threshold → 10d is stale
        git_runner=runner,
        dry_run=False,
    )
    # Assert
    assert out.action == "removed"
    assert any(
        argv[-2:] == ["worktree", "remove"] or argv[-3:-1] == ["worktree", "remove"]
        for argv in runner.calls
    )


def test_gc_one_worktree_honours_dry_run(tmp_path):
    # Arrange
    repo = tmp_path / "proj" / "myrepo"
    wt = repo / ".claude" / "worktrees" / "agent-dry"
    wt.mkdir(parents=True)
    old = time.time() - 10 * 86400
    os.utime(wt, (old, old))
    runner = _ScriptedGitRunner()
    # Act
    out = _worktree_gc._gc_one_worktree(
        repo=str(repo),
        path=str(wt),
        now_epoch=time.time(),
        max_age_seconds=86400.0,
        git_runner=runner,
        dry_run=True,
    )
    # Assert — dry-run reports the intended action but never invokes git.
    assert out.action == "removed"
    assert "dry-run" in out.detail
    assert runner.calls == []


def test_gc_one_worktree_skips_on_git_refusal(tmp_path):
    # Arrange — git refuses (dirty / locked). The worktree must be left
    # alone; the result must be "skipped-refused"; no force happens.
    repo = tmp_path / "proj" / "myrepo"
    wt = repo / ".claude" / "worktrees" / "agent-dirty"
    wt.mkdir(parents=True)
    old = time.time() - 10 * 86400
    os.utime(wt, (old, old))
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-3:-1] == ["worktree", "remove"],
        _FakeCompleted(
            returncode=1, stderr="fatal: working tree is dirty"
        ),
    )
    # Act
    out = _worktree_gc._gc_one_worktree(
        repo=str(repo),
        path=str(wt),
        now_epoch=time.time(),
        max_age_seconds=86400.0,
        git_runner=runner,
        dry_run=False,
    )
    # Assert
    assert out.action == "skipped-refused"
    assert "dirty" in out.detail
    # Worktree directory must still exist — never destroyed by force.
    assert wt.exists()


# ---------------------------------------------------------------------------
# run_once — end-to-end smoke. The hardest invariant: even when a
# repo also has a registered ``.worktrees/`` entry (protected),
# ``git worktree remove`` is NEVER called for it.
# ---------------------------------------------------------------------------


def test_run_once_never_calls_remove_on_protected_path(tmp_path):
    # Arrange — one repo with BOTH a managed and a protected worktree
    # registered. The protected one is stale (so mtime alone would
    # green-light it); the guardrail is what saves it.
    repo = tmp_path / "proj" / "myrepo"
    repo.mkdir(parents=True)
    managed = repo / ".claude" / "worktrees" / "agent-stale"
    managed.mkdir(parents=True)
    protected = repo / ".worktrees" / "operator-x"
    protected.mkdir(parents=True)
    old = time.time() - 10 * 86400
    os.utime(managed, (old, old))
    os.utime(protected, (old, old))

    porcelain = (
        f"worktree {repo}\n"
        "\n"
        f"worktree {managed}\n"
        "\n"
        f"worktree {protected}\n"
    )

    runner = (
        _ScriptedGitRunner()
        .when(
            lambda argv: argv[-3:] == ["worktree", "list", "--porcelain"],
            _FakeCompleted(returncode=0, stdout=porcelain),
        )
        .when(
            # Only the managed path should hit this matcher in argv.
            lambda argv: argv[-2:-1] == ["remove"],
            _FakeCompleted(returncode=0),
        )
        .when(
            lambda argv: argv[-1] == "prune",
            _FakeCompleted(returncode=0),
        )
    )

    out_buf = io.StringIO()
    # Act
    result = _worktree_gc.run_once(
        roots=[str(tmp_path)],
        max_age_days=1.0,
        git_runner=runner,
        out=out_buf,
    )

    # Assert — exactly one removal, and it was the MANAGED worktree.
    assert result.removed == 1
    assert result.scanned == 1  # protected never enters per_worktree
    remove_calls = [
        argv for argv in runner.calls
        if "remove" in argv and "worktree" in argv
    ]
    assert len(remove_calls) == 1
    # The path argument of the remove call MUST be the managed one.
    assert str(managed) in remove_calls[0]
    assert str(protected) not in remove_calls[0]


def test_run_once_skips_when_no_roots_usable(tmp_path):
    # Arrange — point at a non-existent root.
    out_buf = io.StringIO()
    # Act
    result = _worktree_gc.run_once(
        roots=[str(tmp_path / "does-not-exist")],
        max_age_days=1.0,
        git_runner=_ScriptedGitRunner(),
        out=out_buf,
    )
    # Assert
    assert result.error is not None
    assert result.scanned == 0
    assert "no usable search roots" in result.error


def test_run_once_env_var_overrides_threshold(monkeypatch, tmp_path):
    # Arrange — same shape as test_run_once_never_calls_remove_on_protected_path
    # but with the threshold set via env var to a value that should keep
    # the (5-day-old) worktree fresh.
    repo = tmp_path / "proj" / "myrepo"
    managed = repo / ".claude" / "worktrees" / "agent-mediumage"
    managed.mkdir(parents=True)
    old = time.time() - 5 * 86400
    os.utime(managed, (old, old))
    runner = _ScriptedGitRunner().when(
        lambda argv: argv[-3:] == ["worktree", "list", "--porcelain"],
        _FakeCompleted(returncode=0, stdout=f"worktree {managed}\n"),
    )
    monkeypatch.setenv("SCITEX_WORKTREE_GC_MAX_AGE_DAYS", "30")
    out_buf = io.StringIO()
    # Act
    result = _worktree_gc.run_once(
        roots=[str(tmp_path)],
        git_runner=runner,
        out=out_buf,
    )
    # Assert — 30-day threshold, 5-day-old worktree → fresh, no removal.
    assert result.removed == 0
    assert result.skipped_fresh == 1


# EOF
