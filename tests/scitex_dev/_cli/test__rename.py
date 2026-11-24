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


@pytest.fixture
def protected_cli_result(tmp_path):
    target = tmp_path / "cli.py"
    body = 'prog_name="scitex-business"\n'
    target.write_text(body)
    result = CliRunner().invoke(
        main,
        ["rename-symbols", "scitex-business", "scitex-affairs", "--root",
         str(tmp_path), "--dry-run", "--quiet"],
    )
    return result, target, body


def test_quiet_protected_only_exit_code(protected_cli_result):
    # Arrange
    result, _, _ = protected_cli_result
    # Act
    actual = result.exit_code
    # Assert
    assert actual == 0, result.output


def test_quiet_reports_protected_only_count(protected_cli_result):
    # Arrange
    result, _, _ = protected_cli_result
    # Act
    actual = result.output.strip()
    # Assert
    assert actual == "would rename: 0 files / 0 matches / 0 collisions / 1 protected lines"


def test_quiet_protected_only_preserves_file(protected_cli_result):
    # Arrange
    _, target, body = protected_cli_result
    # Act
    actual = target.read_text()
    # Assert
    assert actual == body


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


def test_quiet_one_line_summary_on_dry_run_result_exit_code_0(repo):
    # Arrange
    # Act
    # Assert
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


def test_quiet_one_line_summary_on_dry_run_would_rename_1_files_1_matches_0_collisi(repo):
    # Arrange
    # Act
    # Assert
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
    assert "would rename: 1 files / 1 matches / 0 collisions" in result.output


def test_quiet_one_line_summary_on_real_run_result_exit_code_0(repo):
    # Arrange
    # Act
    # Assert
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


def test_quiet_one_line_summary_on_real_run_renamed_1_files_1_matches_0_collisions_i(repo):
    # Arrange
    # Act
    # Assert
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
    assert "renamed: 1 files / 1 matches / 0 collisions" in result.output


def test_quiet_one_line_summary_on_real_run_repo_a_py_read_text_new_func_n(repo):
    # Arrange
    # Act
    # Assert
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
    assert (repo / "a.py").read_text() == "new_func()\n"


def test_allow_dirty_skips_uncommitted_check_blocked_exit_code_0(repo):
    """Without --allow-dirty, a dirty tree blocks the rename. With the
    flag, the rename proceeds — letting callers chain multiple regex
    passes within one logical change."""
    # Make the tree dirty:
    # Arrange
    # Act
    # Assert
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


def test_allow_dirty_skips_uncommitted_check_uncommitted_changes_in_blocked_output(repo):
    """Without --allow-dirty, a dirty tree blocks the rename. With the
    flag, the rename proceeds — letting callers chain multiple regex
    passes within one logical change."""
    # Make the tree dirty:
    # Arrange
    # Act
    # Assert
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


def test_allow_dirty_skips_uncommitted_check_ok_exit_code_0(repo):
    """Without --allow-dirty, a dirty tree blocks the rename. With the
    flag, the rename proceeds — letting callers chain multiple regex
    passes within one logical change."""
    # Make the tree dirty:
    # Arrange
    # Act
    # Assert
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


def test_allow_dirty_skips_uncommitted_check_repo_a_py_read_text_new_func_nnew_func_n(repo):
    """Without --allow-dirty, a dirty tree blocks the rename. With the
    flag, the rename proceeds — letting callers chain multiple regex
    passes within one logical change."""
    # Make the tree dirty:
    # Arrange
    # Act
    # Assert
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
    assert (repo / "a.py").read_text() == "new_func()\nnew_func()\n"


def test_quiet_reports_zero_matches_cleanly_result_exit_code_0(repo):
    # Arrange
    # Act
    # Assert
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


def test_quiet_reports_zero_matches_cleanly_would_rename_0_files_0_matches_0_collisi(repo):
    # Arrange
    # Act
    # Assert
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
    assert "would rename: 0 files / 0 matches / 0 collisions" in result.output


# EOF



def _rename_verdict_tree_state(base):
    import os

    return {str(f.relative_to(base)): ("link", os.readlink(f)) if f.is_symlink() else ("directory", "") if f.is_dir() else ("file", f.read_text()) for f in base.rglob("*") if ".git" not in f.parts}


@pytest.fixture(params=["dirty", "nonrepo", "file-collision", "directory-link", "clean"])
def _rename_verdict_case(request, tmp_path):
    state = request.param
    root, outside = tmp_path / "repo", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "keep.txt").write_text("KEEP = 1\n")
    if state == "directory-link":
        (root / "alpha_pkg").mkdir()
        (root / "alpha_pkg/module.txt").write_text("VALUE = 1\n")
        (root / "beta_pkg").symlink_to("../outside")
        (root / "notes.txt").write_text("alpha\n")
    else:
        (root / "alpha.txt").write_text("alpha\n")
    if state == "file-collision":
        (root / "beta.txt").write_text("DESTINATION = 2\n")
    if state != "nonrepo":
        _git_init(root)
        _git_commit(root)
    if state == "dirty":
        (root / "alpha.txt").write_text("dirty alpha\n")
    expected = _rename_verdict_tree_state(tmp_path)
    if state == "clean":
        expected["repo/beta.txt"] = ("file", "beta\n")
        del expected["repo/alpha.txt"]
    reasons = {"dirty": "Uncommitted changes", "nonrepo": "not inside a git repository", "file-collision": "Collisions detected", "directory-link": "Collisions detected", "clean": ""}
    return root, state != "clean", reasons[state], expected


def _invoke_rename_verdict(case, flags):
    root, _, _, _ = case
    result = CliRunner().invoke(main, ["rename-symbols", "alpha", "beta", "--root", str(root), "--yes", *flags])
    return case, result


@pytest.fixture(params=[[], ["--quiet"], ["--json"], ["--json", "--quiet"]])
def _rename_verdict_outcome(_rename_verdict_case, request):
    return _invoke_rename_verdict(_rename_verdict_case, request.param)


@pytest.fixture(params=[["--json"], ["--json", "--quiet"]])
def _rename_verdict_json_outcome(_rename_verdict_case, request):
    return _invoke_rename_verdict(_rename_verdict_case, request.param)


def test_rename_verdict_exit_matches_operation_refusal(_rename_verdict_outcome):
    # Arrange
    (_, blocked, _, _), result = _rename_verdict_outcome
    # Act
    actual = result.exit_code
    # Assert
    assert actual == int(blocked)


def test_rename_verdict_preserves_refusals_or_applies_exact_change(_rename_verdict_outcome):
    # Arrange
    (root, _, _, expected), _ = _rename_verdict_outcome
    # Act
    actual = _rename_verdict_tree_state(root.parent)
    # Assert
    assert actual == expected


def test_rename_verdict_json_reports_domain_error(_rename_verdict_json_outcome):
    # Arrange
    import json

    (_, blocked, reason, _), result = _rename_verdict_json_outcome
    # Act
    payload = json.loads(result.stdout)
    # Assert
    assert (payload["success"], bool(payload.get("error")), reason in str(payload.get("error", "")), bool(payload["data"]["error"])) == (not blocked, blocked, True, blocked)
