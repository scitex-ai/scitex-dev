"""Behavioural tests for `scitex-dev ecosystem prune-merged`.

No mocks: each test builds a REAL git repo under `tmp_path` with a
develop branch, a feature branch merged into develop, and an unmerged
feature branch, then drives the command via `click.testing.CliRunner`.
The ECOSYSTEM registry is populated in-process with a temp package
pointing at the real repo (restored afterwards).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _build_repo(repo: Path) -> None:
    """Real repo: develop + a merged branch + an unmerged branch.

    Branches after this:
      develop            (current HEAD)
      feature/merged     (fast-forward merged into develop)
      feature/unmerged   (has a commit not in develop)
      main               (protected; points at first commit)
    """
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test")
    _run_git(repo, "checkout", "-q", "-b", "develop")
    (repo / "f.txt").write_text("base\n")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", "base")

    # protected main pointing at base
    _run_git(repo, "branch", "main")

    # merged branch: branch off, commit, merge back, keep the branch ref
    _run_git(repo, "checkout", "-q", "-b", "feature/merged")
    (repo / "f.txt").write_text("merged-change\n")
    _run_git(repo, "commit", "-aqm", "merged change")
    _run_git(repo, "checkout", "-q", "develop")
    _run_git(repo, "merge", "-q", "--no-ff", "-m", "merge feature", "feature/merged")

    # unmerged branch: commit that never lands on develop
    _run_git(repo, "checkout", "-q", "-b", "feature/unmerged")
    (repo / "g.txt").write_text("unmerged\n")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", "unmerged change")

    # back to develop as the checked-out branch
    _run_git(repo, "checkout", "-q", "develop")


def _branches(repo: Path) -> list[str]:
    out = subprocess.check_output(
        ["git", "-C", str(repo), "branch", "--format=%(refname:short)"], text=True
    )
    return [b.strip() for b in out.splitlines() if b.strip()]


def _invoke_prune(args, *, repo: Path, pkg: str = "pkg-a"):
    """Invoke prune-merged with ECOSYSTEM pointed at one real repo."""
    from scitex_dev._ecosystem import _core

    saved = dict(_core.ECOSYSTEM)
    _core.ECOSYSTEM.clear()
    _core.ECOSYSTEM[pkg] = {
        "local_path": str(repo),
        "import_name": pkg.replace("-", "_"),
        "category": "library",
    }
    try:

        @click.group()
        def main():
            pass

        register_ecosystem_commands(main)
        runner = CliRunner()
        return runner.invoke(
            main, ["ecosystem", "prune-merged", *args], catch_exceptions=False
        )
    finally:
        _core.ECOSYSTEM.clear()
        _core.ECOSYSTEM.update(saved)


def test_prune_merged_dry_run_lists_merged_branch(tmp_path):
    """Dry-run JSON lists the merged feature branch."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    result = _invoke_prune(["-p", "pkg-a", "--json"], repo=repo)
    import json

    branches = [e["branch"] for e in json.loads(result.output)["results"][0]["local"]]
    # Assert
    assert "feature/merged" in branches


def test_prune_merged_dry_run_excludes_unmerged_branch(tmp_path):
    """Dry-run never lists a branch not merged into develop."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    result = _invoke_prune(["-p", "pkg-a", "--json"], repo=repo)
    import json

    branches = [e["branch"] for e in json.loads(result.output)["results"][0]["local"]]
    # Assert
    assert "feature/unmerged" not in branches


def test_prune_merged_dry_run_excludes_protected_develop(tmp_path):
    """Dry-run never lists the protected `develop` branch."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    result = _invoke_prune(["-p", "pkg-a", "--json"], repo=repo)
    import json

    branches = [e["branch"] for e in json.loads(result.output)["results"][0]["local"]]
    # Assert
    assert "develop" not in branches


def test_prune_merged_dry_run_excludes_protected_main(tmp_path):
    """Dry-run never lists the protected `main` branch even if merged."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    result = _invoke_prune(["-p", "pkg-a", "--json"], repo=repo)
    import json

    branches = [e["branch"] for e in json.loads(result.output)["results"][0]["local"]]
    # Assert
    assert "main" not in branches


def test_prune_merged_dry_run_does_not_delete(tmp_path):
    """Dry-run leaves the merged branch present in the repo."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    _invoke_prune(["-p", "pkg-a", "--json"], repo=repo)
    # Assert
    assert "feature/merged" in _branches(repo)


def test_prune_merged_dry_run_action_is_would_delete(tmp_path):
    """Without --apply, the entry action is 'would-delete'."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    result = _invoke_prune(["-p", "pkg-a", "--json"], repo=repo)
    import json

    entry = json.loads(result.output)["results"][0]["local"][0]
    # Assert
    assert entry["action"] == "would-delete"


def test_prune_merged_apply_deletes_merged_branch(tmp_path):
    """`--apply` removes the merged branch from the repo."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    _invoke_prune(["-p", "pkg-a", "--apply", "--json"], repo=repo)
    # Assert
    assert "feature/merged" not in _branches(repo)


def test_prune_merged_apply_keeps_unmerged_branch(tmp_path):
    """`--apply` must never touch an unmerged branch (safe delete)."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    _invoke_prune(["-p", "pkg-a", "--apply", "--json"], repo=repo)
    # Assert
    assert "feature/unmerged" in _branches(repo)


def test_prune_merged_apply_keeps_develop(tmp_path):
    """`--apply` must never delete the develop branch."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    _invoke_prune(["-p", "pkg-a", "--apply", "--json"], repo=repo)
    # Assert
    assert "develop" in _branches(repo)


def test_prune_merged_apply_keeps_main(tmp_path):
    """`--apply` must never delete the protected main branch."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    _invoke_prune(["-p", "pkg-a", "--apply", "--json"], repo=repo)
    # Assert
    assert "main" in _branches(repo)


def test_prune_merged_apply_action_is_deleted(tmp_path):
    """With --apply, the merged entry's action is 'deleted'."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    result = _invoke_prune(["-p", "pkg-a", "--apply", "--json"], repo=repo)
    import json

    entry = json.loads(result.output)["results"][0]["local"][0]
    # Assert
    assert entry["action"] == "deleted"


def test_prune_merged_json_parses(tmp_path):
    """`--json` emits a parseable object exposing the apply flag."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    result = _invoke_prune(["-p", "pkg-a", "--json"], repo=repo)
    import json

    payload = json.loads(result.output)
    # Assert
    assert payload["apply"] is False
