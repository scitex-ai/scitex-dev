# -*- coding: utf-8 -*-
"""Tests for PS-214's new-vs-baseline severity escalation.

Reference: scitex-writer reported that PS-214/PS-215's flat W severity
made both rules invisible in practice — "a finding printed under a green
banner", the exact defect class the rules exist to catch. Their own
`editor = []` sat undetected through repeated audit runs specifically
because nothing distinguished it from routine warning noise. Severity
now depends on whether a violation is genuinely NEW relative to a git
baseline (`develop`) or already pre-existing backlog.

Mirrors the real-git-repo test pattern from
`tests/scitex_dev/_cli/audit/test__diff.py` (`_seed_repo` + real
subprocess git, no mocks) since the escalation helper reuses that
module's `worktree_at` staging primitive.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scitex_dev._cli.audit._project._check_empty_extras import (
    check_ps214_empty_extras,
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


def _write_pyproject(repo: Path, extras_block: str) -> None:
    repo.joinpath("pyproject.toml").write_text(
        "[project]\n"
        'name = "scitex-fakepeer"\n'
        'dependencies = ["numpy"]\n'
        "[project.optional-dependencies]\n"
        f"{extras_block}\n",
        encoding="utf-8",
    )


def _commit_all(repo: Path, message: str) -> None:
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-q", "-m", message)


# --- (a) pre-existing at baseline AND current -> stays W -------------------


def test_ps214_violation_present_in_baseline_stays_warn(tmp_path):
    # Arrange — the baseline (`develop`) commit already ships the empty
    # extra: this is known, not-yet-cleared backlog, not something the
    # change under audit introduced.
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _write_pyproject(repo, "editor = []\n")
    _commit_all(repo, "add empty editor extra")
    out: list = []
    # Act
    check_ps214_empty_extras(repo, Violation, out)
    # Assert
    assert out[0].severity == "W"


# --- (b) new-only-in-current -> escalated to E ------------------------------


def test_ps214_violation_new_since_baseline_is_escalated_to_error(tmp_path):
    # Arrange — baseline has no empty extras at all.
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _write_pyproject(repo, 'full = ["scitex-app>=0.1.0"]\n')
    _commit_all(repo, "baseline: no empty extras")
    # The change under audit introduces a brand-new empty extra.
    _write_pyproject(repo, 'full = ["scitex-app>=0.1.0"]\neditor = []\n')
    out: list = []
    # Act
    check_ps214_empty_extras(repo, Violation, out)
    # Assert
    assert out[0].severity == "E"


# --- (c) pre-existing, untouched by the current diff -> stays W ------------


def test_ps214_pre_existing_violation_not_escalated_by_unrelated_change(tmp_path):
    # Arrange — baseline already carries the empty extra.
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _write_pyproject(repo, "editor = []\n")
    _commit_all(repo, "add empty editor extra")
    # The change under audit touches an UNRELATED file only; the empty
    # extra itself is untouched. Must NOT be mistaken for new debt.
    repo.joinpath("README.md").write_text("seed\nunrelated change\n", encoding="utf-8")
    out: list = []
    # Act
    check_ps214_empty_extras(repo, Violation, out)
    # Assert
    assert out[0].severity == "W"


# EOF
