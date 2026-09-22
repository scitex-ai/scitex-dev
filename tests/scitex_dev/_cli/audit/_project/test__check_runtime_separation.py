"""Tests for PS-180 — per-package `runtime/` separation discipline.

Card: ``ecosystem-runtime-separation``. Invariant: a package's
``src/<pkg>/runtime/`` directory must be excluded by some `.gitignore`
in the package tree (repo-root or ``src/<pkg>/.gitignore``). Runtime
artefacts (logs, caches, generated state) are user-state, not source.

No mocks (NM001-003) — real temp dirs + `tmp_path`. Single assert per
test (PA-307 §3 STX-TQ007 — one observable per test).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_runtime_separation import (
    check_runtime_separation,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


# ===== helpers =====


def _make_pkg_with_runtime(tmp_path: Path, pkg_name: str = "demo_pkg") -> Path:
    """Set up ``src/<pkg>/runtime/`` (with a sentinel file inside so the
    dir survives any tooling that prunes empties). Returns ``tmp_path``
    so tests can chain it as the repo root.
    """
    runtime = tmp_path / "src" / pkg_name / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "logs.txt").write_text("transient\n")
    return tmp_path


def _findings(repo: Path) -> list[_StubViolation]:
    out: list[_StubViolation] = []
    check_runtime_separation(repo, _StubViolation, out)
    return out


# ===== rule FIRES =====


class TestPS180Fires:
    def test_runtime_exists_no_gitignore_fires(self, tmp_path: Path) -> None:
        # Arrange
        repo = _make_pkg_with_runtime(tmp_path)
        # Act
        out = _findings(repo)
        # Assert
        assert any(v.rule == "PS-180" for v in out)

    def test_runtime_exists_empty_gitignore_fires(self, tmp_path: Path) -> None:
        # Arrange
        repo = _make_pkg_with_runtime(tmp_path)
        (repo / ".gitignore").write_text("# nothing relevant\n*.log\n")
        # Act
        out = _findings(repo)
        # Assert
        assert any(v.rule == "PS-180" for v in out)

    def test_runtime_exists_unrelated_gitignore_entry_fires(
        self, tmp_path: Path
    ) -> None:
        # Arrange — `.gitignore` mentions other paths but not runtime/.
        repo = _make_pkg_with_runtime(tmp_path)
        (repo / ".gitignore").write_text("build/\n*.egg-info/\n.venv/\n")
        # Act
        out = _findings(repo)
        # Assert
        assert any(v.rule == "PS-180" for v in out)

    def test_runtime_exists_finding_path_points_at_runtime_dir(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        repo = _make_pkg_with_runtime(tmp_path, pkg_name="my_pkg")
        # Act
        out = _findings(repo)
        # Assert
        assert any(
            v.rule == "PS-180" and v.where.endswith("src/my_pkg/runtime") for v in out
        )


# ===== rule DOES NOT FIRE when .gitignore covers it =====


class TestPS180CoveredByGitignore:
    def test_bare_runtime_slash_in_root_gitignore_no_fire(self, tmp_path: Path) -> None:
        # Arrange — repo-root `.gitignore` has bare `runtime/`.
        repo = _make_pkg_with_runtime(tmp_path)
        (repo / ".gitignore").write_text("runtime/\n")
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-180" for v in out)

    def test_explicit_src_pkg_runtime_in_root_gitignore_no_fire(
        self, tmp_path: Path
    ) -> None:
        # Arrange — explicit anchored form in root `.gitignore`.
        repo = _make_pkg_with_runtime(tmp_path, pkg_name="my_pkg")
        (repo / ".gitignore").write_text("src/my_pkg/runtime/\n")
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-180" for v in out)

    def test_globstar_runtime_in_root_gitignore_no_fire(self, tmp_path: Path) -> None:
        # Arrange — `**/runtime/` catch-all.
        repo = _make_pkg_with_runtime(tmp_path)
        (repo / ".gitignore").write_text("**/runtime/\n")
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-180" for v in out)

    def test_bare_runtime_in_package_gitignore_no_fire(self, tmp_path: Path) -> None:
        # Arrange — package-level `.gitignore` (preferred form) has `runtime/`.
        repo = _make_pkg_with_runtime(tmp_path, pkg_name="my_pkg")
        (repo / "src" / "my_pkg" / ".gitignore").write_text("runtime/\n")
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-180" for v in out)

    def test_leading_slash_runtime_in_package_gitignore_no_fire(
        self, tmp_path: Path
    ) -> None:
        # Arrange — package-level `.gitignore` with `/runtime/` (anchored
        # at package dir).
        repo = _make_pkg_with_runtime(tmp_path, pkg_name="my_pkg")
        (repo / "src" / "my_pkg" / ".gitignore").write_text("/runtime/\n")
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-180" for v in out)

    def test_globstar_runtime_in_package_gitignore_no_fire(
        self, tmp_path: Path
    ) -> None:
        # Arrange — package-level `.gitignore` with `**/runtime/`.
        repo = _make_pkg_with_runtime(tmp_path, pkg_name="my_pkg")
        (repo / "src" / "my_pkg" / ".gitignore").write_text("**/runtime/\n")
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-180" for v in out)


# ===== rule DOES NOT FIRE when the path doesn't exist =====


class TestPS180NoRuntimeOnDisk:
    def test_pkg_without_runtime_dir_no_fire(self, tmp_path: Path) -> None:
        # Arrange — package exists, no `runtime/` subdir.
        (tmp_path / "src" / "demo_pkg").mkdir(parents=True)
        (tmp_path / "src" / "demo_pkg" / "__init__.py").write_text("")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert not any(v.rule == "PS-180" for v in out)

    def test_no_src_dir_at_all_no_fire(self, tmp_path: Path) -> None:
        # Arrange — empty repo, no `src/`.
        # (nothing on disk)
        # Act
        out = _findings(tmp_path)
        # Assert
        assert not any(v.rule == "PS-180" for v in out)

    def test_runtime_is_a_file_not_dir_no_fire(self, tmp_path: Path) -> None:
        # Arrange — `runtime` exists as a file, not a directory.
        pkg = tmp_path / "src" / "demo_pkg"
        pkg.mkdir(parents=True)
        (pkg / "runtime").write_text("# this is a file, not a dir\\n")
        # Act
        out = _findings(tmp_path)
        # Assert
        assert not any(v.rule == "PS-180" for v in out)


# ===== tracked-source carve-out (git) =====

_GIT = shutil.which("git")

needs_git = pytest.mark.skipif(_GIT is None, reason="git binary required")


def _git_tracked_repo(tmp_path: Path, pkg_name: str = "demo_pkg") -> Path:
    """Init a git repo whose `src/<pkg>/runtime/` holds TRACKED sources."""
    runtime = tmp_path / "src" / pkg_name / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "__init__.py").write_text('"""Live source package."""\\n')
    (runtime / "_periodic.py").write_text("TICK = 60\\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "add", f"src/{pkg_name}/runtime"], cwd=tmp_path, check=True
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "track runtime sources",
        ],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


@needs_git
class TestPS180TrackedSource:
    def test_fully_tracked_runtime_package_no_fire(self, tmp_path: Path) -> None:
        # Arrange — every file under runtime/ is git-tracked: a source
        # package, not transient state.
        repo = _git_tracked_repo(tmp_path)
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-180" for v in out)

    def test_untracked_pycache_alongside_tracked_sources_no_fire(
        self, tmp_path: Path
    ) -> None:
        # Arrange — bytecode caches are build artefacts: untracked
        # `__pycache__/*.pyc` beside tracked sources must not flip the
        # verdict back to firing.
        repo = _git_tracked_repo(tmp_path)
        cache = repo / "src" / "demo_pkg" / "runtime" / "__pycache__"
        cache.mkdir()
        (cache / "_periodic.cpython-312.pyc").write_text("fake bytecode")
        # Act
        out = _findings(repo)
        # Assert
        assert not any(v.rule == "PS-180" for v in out)

    def test_partially_tracked_runtime_still_fires(self, tmp_path: Path) -> None:
        # Arrange — one tracked source plus one untracked artefact: the
        # directory still holds untracked state.
        repo = _git_tracked_repo(tmp_path)
        (repo / "src" / "demo_pkg" / "runtime" / "cache.jsonl").write_text(
            "{}\\n"
        )
        # Act
        out = _findings(repo)
        # Assert
        assert any(v.rule == "PS-180" for v in out)

    def test_untracked_runtime_in_a_git_repo_still_fires(
        self, tmp_path: Path
    ) -> None:
        # Arrange — a git checkout, but runtime/ itself was never added.
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        repo = _make_pkg_with_runtime(tmp_path)
        # Act
        out = _findings(repo)
        # Assert
        assert any(v.rule == "PS-180" for v in out)

    def test_runtime_in_a_non_git_tree_still_fires(
        self, tmp_path: Path
    ) -> None:
        # Arrange — no git metadata at all: "cannot tell" fails open
        # toward the previous behaviour, never a silent pass.
        repo = _make_pkg_with_runtime(tmp_path)
        # Act
        out = _findings(repo)
        # Assert
        assert any(v.rule == "PS-180" for v in out)
