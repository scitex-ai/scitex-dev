# -*- coding: utf-8 -*-
"""Tests for PS-215's new-vs-baseline severity escalation.

See `test__check_empty_extras_severity.py`'s module docstring for the
full rationale (scitex-writer report + reused `worktree_at` mechanism).
This file mirrors that pattern for PS-215, the source-side companion of
PS-214.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scitex_dev._cli.audit._project._check_install_remedy_strings import (
    check_ps215_broken_install_remedy,
)
from scitex_dev._cli.audit._project._violation import Violation


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _seed_repo(repo: Path) -> None:
    """Real git repo with an initial commit on a `develop` branch."""
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "test")
    repo.joinpath("README.md").write_text("seed\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", "seed")
    _run_git(repo, "branch", "-M", "develop")


def _write_pyproject(repo: Path, extras_block: str, *, name: str = "scitex-writer") -> None:
    repo.joinpath("pyproject.toml").write_text(
        "[project]\n"
        f'name = "{name}"\n'
        'dependencies = ["numpy"]\n'
        "[project.optional-dependencies]\n"
        f"{extras_block}\n",
        encoding="utf-8",
    )


def _write_src(repo: Path, body: str, *, import_name: str = "scitex_writer") -> None:
    pkg_dir = repo / "src" / import_name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "_server.py").write_text(body, encoding="utf-8")


def _commit_all(repo: Path, message: str) -> None:
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", message)


_REMEDY_BODY = 'raise RuntimeError("Install with: pip install scitex-writer[editor]")\n'


# --- (a) pre-existing at baseline AND current -> stays W -------------------


def test_ps215_violation_present_in_baseline_stays_warn(tmp_path):
    # Arrange — the baseline (`develop`) commit already ships the dead
    # remedy string: known backlog, not something the change introduced.
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _write_pyproject(repo, "editor = []\n")
    _write_src(repo, _REMEDY_BODY)
    _commit_all(repo, "add dead install remedy")
    out: list = []
    # Act
    check_ps215_broken_install_remedy(repo, "scitex-writer", Violation, out)
    # Assert
    assert out[0].severity == "W"


# --- (b) new-only-in-current -> escalated to E ------------------------------


def test_ps215_violation_new_since_baseline_is_escalated_to_error(tmp_path):
    # Arrange — baseline has no dead remedy string at all.
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _write_pyproject(repo, "editor = []\n")
    _write_src(repo, "def f():\n    return 1\n")
    _commit_all(repo, "baseline: no dead remedy string")
    # The change under audit introduces the dead remedy string.
    _write_src(repo, _REMEDY_BODY)
    out: list = []
    # Act
    check_ps215_broken_install_remedy(repo, "scitex-writer", Violation, out)
    # Assert
    assert out[0].severity == "E"


# --- (c) pre-existing, untouched by the current diff -> stays W ------------


def test_ps215_pre_existing_violation_not_escalated_by_unrelated_change(tmp_path):
    # Arrange — baseline already carries the dead remedy string.
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _write_pyproject(repo, "editor = []\n")
    _write_src(repo, _REMEDY_BODY)
    _commit_all(repo, "add dead install remedy")
    # The change under audit touches an UNRELATED file only; the remedy
    # string itself is untouched. Must NOT be mistaken for new debt.
    repo.joinpath("README.md").write_text("seed\nunrelated change\n", encoding="utf-8")
    out: list = []
    # Act
    check_ps215_broken_install_remedy(repo, "scitex-writer", Violation, out)
    # Assert
    assert out[0].severity == "W"


# EOF
