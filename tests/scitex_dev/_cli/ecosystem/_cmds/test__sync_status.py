"""Behavioural tests for `scitex-dev ecosystem check-sync`.

No mocks: every test builds REAL git repositories under `tmp_path`
(init, commit on develop, optionally branch off) and drives the command
through `click.testing.CliRunner`. The ECOSYSTEM registry is redirected
at the helper level by registering a temp package whose `local_path`
points at the real repo we just built.
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
    """Run a git command in `repo`, raising on failure."""
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo_on_develop(repo: Path) -> None:
    """Create a real git repo with one commit on a `develop` branch."""
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test")
    _run_git(repo, "checkout", "-q", "-b", "develop")
    (repo / "file.txt").write_text("v1\n")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", "initial")


def _develop_sha(repo: Path) -> str:
    out = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "refs/heads/develop"], text=True
    )
    return out.strip()


def _invoke_sync_status(args, *, packages):
    """Invoke check-sync with ECOSYSTEM pointed at `packages`.

    `packages` is a dict {name: repo_path}. We build a Click group, then
    drive the command; the helper reads the real ECOSYSTEM registry, so
    instead we patch the registry's _core.ECOSYSTEM via the public dict
    by overwriting it — but to avoid mocks we register the temp packages
    directly into the in-process ECOSYSTEM mapping for the duration.
    """
    from scitex_dev._ecosystem import _core

    saved = dict(_core.ECOSYSTEM)
    _core.ECOSYSTEM.clear()
    for name, repo in packages.items():
        _core.ECOSYSTEM[name] = {
            "local_path": str(repo),
            "import_name": name.replace("-", "_"),
            "category": "library",
        }
    try:

        @click.group()
        def main():
            pass

        register_ecosystem_commands(main)
        runner = CliRunner()
        return runner.invoke(
            main, ["ecosystem", "check-sync", *args], catch_exceptions=False
        )
    finally:
        _core.ECOSYSTEM.clear()
        _core.ECOSYSTEM.update(saved)


def test_sync_status_json_reports_local_develop_sha(tmp_path):
    """JSON output carries the real local develop sha for the package."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _init_repo_on_develop(repo)
    expected = _develop_sha(repo)
    # Act
    result = _invoke_sync_status(["-p", "pkg-a", "--json"], packages={"pkg-a": repo})
    import json

    payload = json.loads(result.output)
    # Assert
    assert payload["rows"][0]["local_develop"] == expected


def test_sync_status_json_parses_as_valid_json(tmp_path):
    """`--json` emits a parseable object with a `rows` key."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _init_repo_on_develop(repo)
    # Act
    result = _invoke_sync_status(["-p", "pkg-a", "--json"], packages={"pkg-a": repo})
    import json

    payload = json.loads(result.output)
    # Assert
    assert "rows" in payload


def test_sync_status_local_only_status_is_synced(tmp_path):
    """A clean develop checkout with no hosts classifies as synced."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _init_repo_on_develop(repo)
    # Act
    result = _invoke_sync_status(["-p", "pkg-a", "--json"], packages={"pkg-a": repo})
    import json

    payload = json.loads(result.output)
    # Assert
    assert payload["rows"][0]["status"] == "synced"


def test_sync_status_off_develop_when_branch_not_develop(tmp_path):
    """A repo whose HEAD is on a feature branch is flagged off-develop."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _init_repo_on_develop(repo)
    _run_git(repo, "checkout", "-q", "-b", "feature/x")
    # Act
    result = _invoke_sync_status(["-p", "pkg-a", "--json"], packages={"pkg-a": repo})
    import json

    payload = json.loads(result.output)
    # Assert
    assert payload["rows"][0]["status"] == "off-develop"


def test_sync_status_missing_when_local_path_absent(tmp_path):
    """A package whose local_path does not exist classifies as missing."""
    # Arrange
    absent = tmp_path / "nonexistent"
    # Act
    result = _invoke_sync_status(["-p", "pkg-a", "--json"], packages={"pkg-a": absent})
    import json

    payload = json.loads(result.output)
    # Assert
    assert payload["rows"][0]["status"] == "missing"


def test_sync_status_table_renders_package_name(tmp_path):
    """The default table output includes the package name."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _init_repo_on_develop(repo)
    # Act
    result = _invoke_sync_status(["-p", "pkg-a"], packages={"pkg-a": repo})
    # Assert
    assert "pkg-a" in result.output


def test_sync_status_classify_equal_shas_is_synced():
    """_classify returns 'synced' when both develop shas are identical."""
    # Arrange
    from scitex_dev._cli.ecosystem._cmds._sync_status import _classify

    sha = "a" * 40
    # Act
    status = _classify(None, sha, sha)
    # Assert
    assert status == "synced"


def test_sync_status_classify_one_missing_is_differs():
    """_classify returns 'differs' when only one sha is present."""
    # Arrange
    from scitex_dev._cli.ecosystem._cmds._sync_status import _classify

    # Act
    status = _classify(None, "a" * 40, "")
    # Assert
    assert status == "differs"


def test_sync_status_classify_both_missing_is_missing():
    """_classify returns 'missing' when neither sha is present."""
    # Arrange
    from scitex_dev._cli.ecosystem._cmds._sync_status import _classify

    # Act
    status = _classify(None, "", "")
    # Assert
    assert status == "missing"


def test_sync_status_classify_behind_when_remote_is_ahead(tmp_path):
    """_classify returns 'behind' when the remote sha is an ancestor's child.

    Both commits live in one real repo: an older HEAD (local) and a
    newer HEAD (remote). local..remote has one commit -> behind.
    """
    # Arrange
    from scitex_dev._cli.ecosystem._cmds._sync_status import _classify

    repo = tmp_path / "pkg-a"
    _init_repo_on_develop(repo)
    local_sha = _develop_sha(repo)
    (repo / "file.txt").write_text("v2\n")
    _run_git(repo, "commit", "-aqm", "second")
    remote_sha = _develop_sha(repo)
    # Act
    status = _classify(repo, local_sha, remote_sha)
    # Assert
    assert status == "behind"


def test_sync_status_classify_ahead_when_local_is_newer(tmp_path):
    """_classify returns 'ahead' when local has commits remote lacks."""
    # Arrange
    from scitex_dev._cli.ecosystem._cmds._sync_status import _classify

    repo = tmp_path / "pkg-a"
    _init_repo_on_develop(repo)
    remote_sha = _develop_sha(repo)
    (repo / "file.txt").write_text("v2\n")
    _run_git(repo, "commit", "-aqm", "second")
    local_sha = _develop_sha(repo)
    # Act
    status = _classify(repo, local_sha, remote_sha)
    # Assert
    assert status == "ahead"


def test_sync_status_classify_diverged_when_histories_fork(tmp_path):
    """_classify returns 'diverged' when each side has unique commits."""
    # Arrange
    from scitex_dev._cli.ecosystem._cmds._sync_status import _classify

    repo = tmp_path / "pkg-a"
    _init_repo_on_develop(repo)
    base = _develop_sha(repo)
    # local branch: one unique commit
    _run_git(repo, "checkout", "-q", "-b", "local-line")
    (repo / "file.txt").write_text("local\n")
    _run_git(repo, "commit", "-aqm", "local")
    local_sha = _develop_sha(repo)  # still base; capture branch tip below
    local_sha = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    # remote line: a different unique commit off the same base
    _run_git(repo, "checkout", "-q", base)
    _run_git(repo, "checkout", "-q", "-b", "remote-line")
    (repo / "file.txt").write_text("remote\n")
    _run_git(repo, "commit", "-aqm", "remote")
    remote_sha = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    # Act
    status = _classify(repo, local_sha, remote_sha)
    # Assert
    assert status == "diverged"
