#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The `branch-gc` cron body.

The property that matters most here is the one that is easy to lose in a
refactor: INSTALLING THIS JOB ARMS NOTHING. The body runs, reads every
managed checkout, prints what it saw, and deletes nothing until each repo
opts in on both config surfaces.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from scitex_dev._cli.cron import _branch_gc


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _build_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    _git(repo, "checkout", "-q", "-b", "develop")
    (repo / "f.txt").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "feature/old", "develop")
    _git(repo, "checkout", "-q", "develop")


def _run_with_ecosystem(repo: Path) -> tuple[str, object]:
    """Run the body with ECOSYSTEM pointed at one real repo (restored after)."""
    from scitex_dev._ecosystem import _core

    saved = dict(_core.ECOSYSTEM)
    _core.ECOSYSTEM.clear()
    _core.ECOSYSTEM["pkg-a"] = {
        "local_path": str(repo),
        "import_name": "pkg_a",
        "category": "library",
    }
    sink = io.StringIO()
    try:
        result = _branch_gc.run_once(out=sink)
    finally:
        _core.ECOSYSTEM.clear()
        _core.ECOSYSTEM.update(saved)
    return sink.getvalue(), result


def _branches(repo: Path) -> list[str]:
    out = subprocess.check_output(
        ["git", "-C", str(repo), "branch", "--format=%(refname:short)"], text=True
    )
    return [b.strip() for b in out.splitlines() if b.strip()]


def test_run_once_deletes_nothing_on_an_unconfigured_repo(tmp_path):
    """THE PROPERTY: installing the job arms nothing anywhere."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    before = _branches(repo)
    # Act
    _run_with_ecosystem(repo)
    # Assert
    assert _branches(repo) == before


def test_run_once_reports_the_repo_as_off(tmp_path):
    """A log full of no-ops must be legible, not mysterious."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    output, _ = _run_with_ecosystem(repo)
    # Assert
    assert "off " in output


def test_run_once_counts_the_repo_it_visited(tmp_path):
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    _, result = _run_with_ecosystem(repo)
    # Assert
    assert result.repos == 1


def test_run_once_does_not_fail_the_cron_loop_on_a_no_op_pass(tmp_path):
    """`failed` means the WHOLE pass could not run — not "nothing to do"."""
    # Arrange
    repo = tmp_path / "pkg-a"
    _build_repo(repo)
    # Act
    _, result = _run_with_ecosystem(repo)
    # Assert
    assert result.failed is False


def test_run_once_fails_loudly_when_no_checkout_exists():
    """An empty ecosystem is a real failure, not a silent green pass."""
    # Arrange
    from scitex_dev._ecosystem import _core

    saved = dict(_core.ECOSYSTEM)
    _core.ECOSYSTEM.clear()
    sink = io.StringIO()
    try:
        # Act
        result = _branch_gc.run_once(out=sink)
    finally:
        _core.ECOSYSTEM.clear()
        _core.ECOSYSTEM.update(saved)
    # Assert
    assert result.failed is True


# EOF
