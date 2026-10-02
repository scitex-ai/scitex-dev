#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for home._managed_by_git (real git, real tmp homes, no mocks)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scitex_dev.home import ensure_dotscitex_managed_by_git

TRACK = ("agent-container/agents/*/spec.yaml", "agent-container/config.yaml")


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert proc.returncode == 0, proc.stderr[:200]
    return proc.stdout.strip()


def _seed_home(home: Path) -> None:
    scitex = home / ".scitex"
    (scitex / "agent-container" / "agents" / "demo").mkdir(parents=True)
    (scitex / "agent-container" / "agents" / "demo" / "spec.yaml").write_text("name: demo\n")
    (scitex / "agent-container" / "config.yaml").write_text("peers: {}\n")
    (scitex / "agent-container" / "agents" / "demo" / "session.jsonl").write_text("{}\n")
    (scitex / "agent-container" / "agents" / "demo" / "boot.stdout.log").write_text("x\n")
    (scitex / "cards").mkdir(parents=True)
    (scitex / "cards" / "token.secret").write_text("SECRET\n")


def test_adopt_existing_home_commits_specs_not_runtime(tmp_path):
    # Arrange — a lived-in home with specs, runtime files and a secret.
    _seed_home(tmp_path)
    root = tmp_path / ".scitex"
    # Act
    out = ensure_dotscitex_managed_by_git(tmp_path, track=TRACK)
    # Assert — specs committed; runtime + secret never tracked.
    assert out["initialized"] is True
    assert out["committed"] is True
    assert len(str(out["head"])) == 40
    tracked = set(_git(root, "ls-files").split())
    assert "agent-container/agents/demo/spec.yaml" in tracked
    assert "agent-container/config.yaml" in tracked
    assert ".gitignore" in tracked
    assert not any("session.jsonl" in t or ".log" in t for t in tracked)
    assert not any("secret" in t for t in tracked)
    assert not any("/runtime/" in t for t in tracked)


def test_runtime_files_migrated_with_symlink_left_behind(tmp_path):
    # Arrange
    _seed_home(tmp_path)
    # Act
    out = ensure_dotscitex_managed_by_git(tmp_path, track=TRACK)
    demo = tmp_path / ".scitex" / "agent-container" / "agents" / "demo"
    # Assert — moved under agent-container/runtime/, symlink at old path.
    assert (tmp_path / ".scitex" / "agent-container" / "runtime" / "agents" / "demo" / "session.jsonl").is_file()
    assert (demo / "session.jsonl").is_symlink()
    assert any("session.jsonl" in m for m in out["runtime_migrated"])


def test_second_run_is_a_no_op(tmp_path):
    # Arrange — managed once already.
    _seed_home(tmp_path)
    first = ensure_dotscitex_managed_by_git(tmp_path, track=TRACK)
    # Act
    second = ensure_dotscitex_managed_by_git(tmp_path, track=TRACK)
    # Assert — nothing new staged or committed.
    assert second["initialized"] is False
    assert second["committed"] is False
    assert second["head"] == first["head"]
    assert second["runtime_migrated"] == []
    assert second["clean"] is True


def test_dirty_spec_is_recommitted(tmp_path):
    # Arrange — managed, then the spec changes.
    _seed_home(tmp_path)
    first = ensure_dotscitex_managed_by_git(tmp_path, track=TRACK)
    (tmp_path / ".scitex" / "agent-container" / "config.yaml").write_text("peers: {a: b}\n")
    # Act
    second = ensure_dotscitex_managed_by_git(tmp_path, track=TRACK)
    # Assert — the spec change is committed, HEAD moves.
    assert second["committed"] is True
    assert second["head"] != first["head"]
    assert second["clean"] is True


def test_nested_repo_untracked_content_neither_blocks_nor_commits(tmp_path):
    # Arrange — managed home containing a nested vcs repo with untracked
    # debris (preserved snapshots, live overlay junk). Regression: porcelain
    # noise used to trigger a commit attempt with an empty index, failing
    # the whole launch preflight.
    _seed_home(tmp_path)
    first = ensure_dotscitex_managed_by_git(tmp_path, track=TRACK)
    nested = tmp_path / ".scitex" / "agent-container" / ".old" / "preserved"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(nested)], check=True, timeout=60)
    subprocess.run(["git", "-C", str(nested), "config", "user.email", "t@t"],
                   check=True, timeout=60)
    subprocess.run(["git", "-C", str(nested), "config", "user.name", "t"],
                   check=True, timeout=60)
    (nested / "kept.txt").write_text("kept\n")
    subprocess.run(["git", "-C", str(nested), "add", "-A"], check=True, timeout=60)
    subprocess.run(["git", "-C", str(nested), "commit", "-qm", "seed"],
                   check=True, timeout=60)
    # Settle the new gitlink first (legitimate commit of new content).
    mid = ensure_dotscitex_managed_by_git(tmp_path, track=TRACK)
    assert mid["committed"] is True
    # Now add untracked debris inside the nested repo (the launch-time noise).
    (nested / "debris.tmp").write_text("junk\n")
    # Act — must not raise, must not commit.
    second = ensure_dotscitex_managed_by_git(tmp_path, track=TRACK)
    # Assert — no commit (nothing stageable), HEAD unmoved.
    assert second["committed"] is False
    assert second["head"] == mid["head"]


def _write_git_shim(path: Path, real_git: str) -> None:
    # Forwarding executable: delegates every invocation to the real git
    # except the staged probe, which fails with $FAKE_GIT_DIFF_CODE when set.
    path.write_text(
        "#!/bin/sh\n"
        'case " $* " in\n'
        '  *" diff --cached --name-only -z "*) code="${FAKE_GIT_DIFF_CODE:-}"\n'
        '    if [ -n "$code" ]; then echo "${FAKE_GIT_DIFF_ERR:-fatal: injected}" >&2; exit "$code"; fi;;\n'
        "esac\n"
        f'exec "{real_git}" "$@"\n'
    )
    path.chmod(0o755)


def test_staged_probe_real_empty_staged_whitespace(tmp_path, monkeypatch):
    # Real git, real index: empty -> False; staged file (whitespace name) -> True.
    import scitex_dev.home._managed_by_git as m
    _seed_home(tmp_path)
    root = tmp_path / ".scitex"
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, timeout=60)
    assert m._index_has_staged_changes(root) is False
    weird = root / "agent-container" / "agents" / "my agent"
    weird.mkdir(parents=True)
    (weird / "spec.yaml").write_text("name: weird\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, timeout=60)
    assert m._index_has_staged_changes(root) is True


def test_staged_probe_failure_codes_propagate(tmp_path, monkeypatch):
    # Forwarding shim: exit 1/2/128 on the probe must all raise (no silent
    # acceptance); passthrough forwards the real answer.
    import os
    import shutil
    import scitex_dev.home._managed_by_git as m
    _seed_home(tmp_path)
    root = tmp_path / ".scitex"
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, timeout=60)
    real_git = shutil.which("git")
    assert real_git
    shimdir = tmp_path / "shimbin"
    shimdir.mkdir()
    _write_git_shim(shimdir / "git", real_git)
    monkeypatch.setenv("PATH", str(shimdir) + os.pathsep + os.environ["PATH"])
    # Passthrough proves forwarding: real empty index -> False.
    monkeypatch.delenv("FAKE_GIT_DIFF_CODE", raising=False)
    assert m._index_has_staged_changes(root) is False
    for code in (1, 2, 128):
        monkeypatch.setenv("FAKE_GIT_DIFF_CODE", str(code))
        try:
            m._index_has_staged_changes(root)
        except RuntimeError as exc:
            assert "diff --cached --name-only" in str(exc)
        else:
            raise AssertionError(f"exit-{code} diff must raise")


def test_user_gitignore_lines_are_preserved(tmp_path):
    # Arrange — a pre-existing repo with the user's own ignore line.
    _seed_home(tmp_path)
    root = tmp_path / ".scitex"
    _git(root, "init", "-q") if False else subprocess.run(
        ["git", "init", "-q", str(root)], check=True, timeout=60
    )
    (root / ".gitignore").write_text("# my own\n*.bak\n")
    # Act
    ensure_dotscitex_managed_by_git(tmp_path, track=TRACK)
    # Assert — user lines survive alongside the managed block.
    text = (root / ".gitignore").read_text()
    assert "*.bak" in text
    assert "scitex-dev: managed block" in text


def test_extra_ignore_keeps_package_runtime_dirs_untracked(tmp_path):
    # Arrange — a package overlay dir that must never commit.
    _seed_home(tmp_path)
    overlay = tmp_path / ".scitex" / "agent-container" / "containers" / "overlays" / "demo"
    overlay.mkdir(parents=True)
    (overlay / "rootfs.img").write_text("BINARY\n")
    # Act
    out = ensure_dotscitex_managed_by_git(
        tmp_path, track=TRACK, extra_ignore=("agent-container/containers/",)
    )
    root = tmp_path / ".scitex"
    # Assert — overlay content never tracked, repo still commits specs.
    assert out["committed"] is True
    tracked = set(_git(root, "ls-files").split())
    assert not any("overlays" in t for t in tracked)
    assert "agent-container/agents/demo/spec.yaml" in tracked


def test_custom_commit_message_is_used(tmp_path):
    # Arrange
    _seed_home(tmp_path)
    # Act
    ensure_dotscitex_managed_by_git(tmp_path, track=TRACK, commit_message="sac: adopt home specs")
    # Assert
    msg = _git(tmp_path / ".scitex", "log", "--format=%s", "-1")
    assert msg == "sac: adopt home specs"


def test_nested_repo_with_unborn_head_inside_ignored_dir_does_not_fail(tmp_path):
    # Arrange — an agent scratchpad: nested repo, never committed (add -A
    # dies fatal on these when git descends into them).
    import subprocess

    _seed_home(tmp_path)
    nest = tmp_path / ".scitex" / "agent-container" / "containers" / "ov" / "scratchpad" / "proj"
    nest.mkdir(parents=True)
    (nest / "notes.txt").write_text("work\n")
    subprocess.run(["git", "init", "-q", str(nest)], check=True, timeout=60)
    # Act — must not raise; the ignored subtree is pruned, never walked.
    out = ensure_dotscitex_managed_by_git(
        tmp_path, track=TRACK, extra_ignore=("agent-container/containers/",)
    )
    root = tmp_path / ".scitex"
    # Assert — home commits; nothing under containers/ tracked.
    assert out["committed"] is True
    tracked = set(_git(root, "ls-files").split())
    assert not any("containers" in t for t in tracked)
    assert "agent-container/agents/demo/spec.yaml" in tracked


def test_nested_repo_under_runtime_is_pruned(tmp_path):
    # Arrange — nested repo directly under a <pkg>/runtime/ dir.
    import subprocess

    _seed_home(tmp_path)
    nest = tmp_path / ".scitex" / "agent-container" / "runtime" / "sess" / "repo"
    nest.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(nest)], check=True, timeout=60)
    # Act / Assert — no failure, runtime content never tracked.
    out = ensure_dotscitex_managed_by_git(tmp_path, track=TRACK)
    assert out["committed"] is True
    tracked = set(_git(tmp_path / ".scitex", "ls-files").split())
    assert not any("/runtime/" in t for t in tracked)
