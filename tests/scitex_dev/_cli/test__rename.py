"""Tests for ``scitex-dev rename-symbols`` — focused on the two new
ergonomic flags landed alongside the extraction into _cli/_rename.py.

* ``--allow-dirty`` — chain multi-pattern renames within one logical
  change without committing between each pass.
* ``--quiet`` / ``-q`` — one-line ``N files / M matches / K collisions``
  summary instead of the full RenameResult repr.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytest.importorskip("click")

from click.testing import CliRunner

from scitex_dev._cli._root import main


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)


def _git_commit(repo: Path, message: str = "snap") -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", message], check=True)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "a.py").write_text("old_func()\n")
    _git_init(tmp_path)
    _git_commit(tmp_path, "init")
    return tmp_path


def test_quiet_one_line_summary_on_dry_run(repo):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "rename-symbols",
            "old_func",
            "new_func",
            "--root",
            str(repo),
            "--dry-run",
            "-q",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "would rename: 1 files / 1 matches / 0 collisions" in result.output


def test_quiet_one_line_summary_on_real_run(repo):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "rename-symbols",
            "old_func",
            "new_func",
            "--root",
            str(repo),
            "-q",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "renamed: 1 files / 1 matches / 0 collisions" in result.output
    assert (repo / "a.py").read_text() == "new_func()\n"


def test_allow_dirty_skips_uncommitted_check(repo):
    """Without --allow-dirty, a dirty tree blocks the rename. With the
    flag, the rename proceeds — letting callers chain multiple regex
    passes within one logical change."""
    # Make the tree dirty:
    (repo / "a.py").write_text("old_func()\nold_func()\n")

    runner = CliRunner()

    # Without --allow-dirty: should report the uncommitted-changes error.
    blocked = runner.invoke(
        main,
        [
            "rename-symbols",
            "old_func",
            "new_func",
            "--root",
            str(repo),
            "-q",
        ],
    )
    assert blocked.exit_code != 0
    assert "Uncommitted changes" in blocked.output

    # With --allow-dirty: succeeds, file is rewritten.
    ok = runner.invoke(
        main,
        [
            "rename-symbols",
            "old_func",
            "new_func",
            "--root",
            str(repo),
            "-q",
            "--allow-dirty",
        ],
    )
    assert ok.exit_code == 0, ok.output
    assert (repo / "a.py").read_text() == "new_func()\nnew_func()\n"


def test_quiet_reports_zero_matches_cleanly(repo):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "rename-symbols",
            "no_such_symbol",
            "new",
            "--root",
            str(repo),
            "--dry-run",
            "-q",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "would rename: 0 files / 0 matches / 0 collisions" in result.output


# EOF
