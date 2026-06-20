# -*- coding: utf-8 -*-
"""Tests for `_check_umbrella_dep_and_integration.py` (PS-139 / PS-140).

PS-139 bans leaf/standalone packages from listing `scitex` (the umbrella)
in their dependencies. The umbrella *itself* is exempt — its recursive
`scitex[<extra>]` self-references in `pyproject.toml` are how `[all]`
aggregates every peer extra (the documented umbrella-passthrough pattern),
not "umbrella drag."

The exemption used to compare `repo.resolve()` against the ECOSYSTEM
`local_path` with **exact path equality**. That breaks for every git
worktree (`<repo>/.worktrees/<name>`), which is exactly how agents and the
operator run the audit — so PS-139/PS-140 fired ~77 false positives on the
umbrella's own self-extras. These tests pin the three exemption signals:
registry path, main-worktree resolution, and the `[project].name == "scitex"`
backstop. Real temp packages and real `git worktree` checkouts — no mocks.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_umbrella_dep_and_integration import (
    _is_umbrella,
    _main_worktree_root,
    _pyproject_distribution_name,
    check_ps139_umbrella_dep,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _codes(out: list) -> set[str]:
    return {v.rule for v in out}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_git_repo(repo: Path, *, name: str, body: str | None = None) -> None:
    """Materialize a real committed git repo with a pyproject `[project].name`."""
    repo.mkdir(parents=True, exist_ok=True)
    _write(
        repo / "pyproject.toml",
        body if body is not None else f'[project]\nname = "{name}"\n',
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")


# --- _pyproject_distribution_name -------------------------------------------


def test_pyproject_distribution_name_reads_project_name(tmp_path):
    # Arrange
    _write(tmp_path / "pyproject.toml", '[project]\nname = "scitex-foo"\n')
    # Act
    name = _pyproject_distribution_name(tmp_path)
    # Assert
    assert name == "scitex-foo"


def test_pyproject_distribution_name_none_when_file_absent(tmp_path):
    # Arrange — empty dir, no pyproject
    # Act
    name = _pyproject_distribution_name(tmp_path)
    # Assert
    assert name is None


def test_pyproject_distribution_name_none_when_name_missing(tmp_path):
    # Arrange — pyproject without a [project].name
    _write(tmp_path / "pyproject.toml", "[build-system]\nrequires = []\n")
    # Act
    name = _pyproject_distribution_name(tmp_path)
    # Assert
    assert name is None


# --- _main_worktree_root ----------------------------------------------------


def test_main_worktree_root_of_main_checkout_is_itself(tmp_path):
    # Arrange — a plain git repo (no linked worktrees)
    repo = tmp_path / "scitex-python"
    _make_git_repo(repo, name="scitex")
    # Act
    root = _main_worktree_root(repo)
    # Assert
    assert root is not None and root.resolve() == repo.resolve()


def test_main_worktree_root_of_linked_worktree_points_to_main(tmp_path):
    # Arrange — main repo + a linked worktree under .worktrees/
    repo = tmp_path / "scitex-python"
    _make_git_repo(repo, name="scitex")
    wt = repo / ".worktrees" / "full-green"
    _git(repo, "worktree", "add", "-q", str(wt))
    # Act
    root = _main_worktree_root(wt)
    # Assert
    assert root is not None and root.resolve() == repo.resolve()


def test_main_worktree_root_none_outside_git(tmp_path):
    # Arrange — a bare directory, not a git checkout
    # Act
    root = _main_worktree_root(tmp_path)
    # Assert
    assert root is None


# --- _is_umbrella -----------------------------------------------------------


def test_is_umbrella_true_via_pyproject_name(tmp_path):
    # Arrange — `[project].name == "scitex"` is the path-independent backstop
    _write(tmp_path / "pyproject.toml", '[project]\nname = "scitex"\n')
    # Act
    result = _is_umbrella(tmp_path)
    # Assert
    assert result is True


def test_is_umbrella_true_for_worktree_of_umbrella(tmp_path):
    # Arrange — a linked worktree whose main checkout's pyproject is `scitex`.
    # This is the regression the fix targets: the worktree path differs from
    # the registered local_path, but the main working tree resolves to the
    # umbrella, so the exemption must still fire.
    repo = tmp_path / "scitex-python"
    _make_git_repo(repo, name="scitex")
    wt = repo / ".worktrees" / "full-green"
    _git(repo, "worktree", "add", "-q", str(wt))
    # Act
    result = _is_umbrella(wt)
    # Assert
    assert result is True


def test_is_umbrella_false_for_leaf_package(tmp_path):
    # Arrange — a normal standalone peer
    _write(tmp_path / "pyproject.toml", '[project]\nname = "scitex-io"\n')
    # Act
    result = _is_umbrella(tmp_path)
    # Assert
    assert result is False


def test_is_umbrella_false_for_worktree_of_leaf(tmp_path):
    # Arrange — worktree of a *leaf* repo must stay non-umbrella (the fix must
    # not over-match every worktree to the umbrella).
    repo = tmp_path / "scitex-io"
    _make_git_repo(repo, name="scitex-io")
    wt = repo / ".worktrees" / "feature"
    _git(repo, "worktree", "add", "-q", str(wt))
    # Act
    result = _is_umbrella(wt)
    # Assert
    assert result is False


# --- PS-139 integration: fires for leaf, silent for umbrella ----------------


def test_ps139_fires_for_leaf_depending_on_umbrella_extra(tmp_path):
    # Arrange — a leaf peer that lists `scitex[io]` (real umbrella drag)
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "scitex-foo"\n'
        '[project.optional-dependencies]\nx = ["scitex[io]>=2.0"]\n',
    )
    out: list = []
    # Act
    check_ps139_umbrella_dep(tmp_path, _StubViolation, out)
    # Assert
    assert "PS-139" in _codes(out)


def test_ps139_fires_for_leaf_with_hard_umbrella_dep(tmp_path):
    # Arrange — leaf with a HARD runtime dep on the umbrella
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "scitex-bar"\ndependencies = ["scitex>=2.0", "numpy"]\n',
    )
    out: list = []
    # Act
    check_ps139_umbrella_dep(tmp_path, _StubViolation, out)
    # Assert
    assert "PS-139" in _codes(out)


def test_ps139_silent_for_umbrella_self_extras_via_pyproject_name(tmp_path):
    # Arrange — the umbrella aggregating its own extras (the legit pattern).
    # `[project].name == "scitex"` makes the exemption fire even off-registry.
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "scitex"\n'
        "[project.optional-dependencies]\n"
        'all = ["scitex[io]", "scitex[plt]", "scitex[stats]"]\n',
    )
    out: list = []
    # Act
    check_ps139_umbrella_dep(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps139_silent_for_umbrella_worktree_self_extras(tmp_path):
    # Arrange — the exact failing scenario: audit the umbrella from a linked
    # worktree. Self-extras must NOT be flagged (was ~76 false positives).
    repo = tmp_path / "scitex-python"
    _make_git_repo(
        repo,
        name="scitex",
        body=(
            '[project]\nname = "scitex"\n'
            "[project.optional-dependencies]\n"
            'all = ["scitex[io]", "scitex[plt]"]\nrng = ["scitex[repro]"]\n'
        ),
    )
    wt = repo / ".worktrees" / "full-green"
    _git(repo, "worktree", "add", "-q", str(wt))
    out: list = []
    # Act
    check_ps139_umbrella_dep(wt, _StubViolation, out)
    # Assert
    assert out == []


def test_ps139_silent_when_no_umbrella_dep(tmp_path):
    # Arrange — leaf with only third-party deps
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "scitex-baz"\ndependencies = ["numpy", "pandas"]\n',
    )
    out: list = []
    # Act
    check_ps139_umbrella_dep(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


# EOF
