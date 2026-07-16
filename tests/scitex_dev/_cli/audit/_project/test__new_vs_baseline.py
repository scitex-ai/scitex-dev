# -*- coding: utf-8 -*-
"""Unit tests for `_new_vs_baseline.escalate_new_violations`.

The general escalation-mechanism tests (independent of any specific
rule); PS-214/PS-215's own integration coverage lives in
`test__check_empty_extras_severity.py` and
`test__check_install_remedy_strings_severity.py`.

Mirrors the real-git-repo pattern from `tests/scitex_dev/_cli/audit/
test__diff.py` (`_seed_repo` + real subprocess git, no mocks) since this
module reuses that module's `worktree_at` staging primitive.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scitex_dev._cli.audit._project._new_vs_baseline import escalate_new_violations
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


def test_escalate_new_violations_noop_without_git_history(tmp_path):
    """No `.git` at all (a plain unit-test fixture) → no escalation, the
    violation keeps the rule's default severity."""
    # Arrange
    repo = tmp_path / "repo"
    repo.mkdir()
    current = [Violation("PS-214", "pyproject.toml", "detail")]
    # Act
    escalate_new_violations(repo, current, ("PS-214",), lambda base: [])
    # Assert
    assert current[0].severity_override is None


def test_escalate_new_violations_noop_when_baseline_ref_unresolvable(tmp_path):
    """A real git repo, but the baseline ref doesn't exist anywhere
    (neither `develop` nor `origin/develop`) → no escalation."""
    # Arrange
    repo = tmp_path / "repo"
    _seed_repo(repo)
    _run_git(repo, "branch", "-M", "main")  # rename away from "develop"
    current = [Violation("PS-214", "pyproject.toml", "detail")]
    # Act
    escalate_new_violations(repo, current, ("PS-214",), lambda base: [])
    # Assert
    assert current[0].severity_override is None


def test_escalate_new_violations_escalates_when_absent_from_baseline(tmp_path):
    """A violation absent from the baseline recheck is genuinely new."""
    # Arrange
    repo = tmp_path / "repo"
    _seed_repo(repo)
    current = [Violation("PS-214", "pyproject.toml", "detail")]
    # Act
    escalate_new_violations(repo, current, ("PS-214",), lambda base: [])
    # Assert
    assert current[0].severity_override == "E"


def test_escalate_new_violations_leaves_matching_baseline_violation_alone(tmp_path):
    """A violation whose identity also appears in the baseline recheck
    stays at the rule's default (no override set)."""
    # Arrange
    repo = tmp_path / "repo"
    _seed_repo(repo)
    current = [Violation("PS-214", "pyproject.toml", "detail")]

    def _recheck(base_repo: Path) -> list:
        return [Violation("PS-214", "pyproject.toml", "detail")]

    # Act
    escalate_new_violations(repo, current, ("PS-214",), _recheck)
    # Assert
    assert current[0].severity_override is None


def test_escalate_new_violations_ignores_untargeted_rule_codes(tmp_path):
    """Only violations whose rule is in `rule_codes` are touched."""
    # Arrange
    repo = tmp_path / "repo"
    _seed_repo(repo)
    current = [Violation("PS-999", "pyproject.toml", "detail")]
    # Act
    escalate_new_violations(repo, current, ("PS-214",), lambda base: [])
    # Assert
    assert current[0].severity_override is None


def test_escalate_new_violations_falls_back_to_origin_prefixed_ref(tmp_path):
    """CI checkouts (`fetch-depth: 0`) typically only carry the
    remote-tracking `origin/develop`, not a local `develop` branch. The
    escalation helper must still resolve via the `origin/<ref>` fallback."""
    # Arrange — repo whose ONLY reachable "develop" is origin/develop.
    repo = tmp_path / "repo"
    _seed_repo(repo)  # HEAD is on local `develop`
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    _run_git(repo, "remote", "add", "origin", str(remote))
    _run_git(repo, "push", "-q", "origin", "develop")
    _run_git(repo, "fetch", "-q", "origin", "develop")
    _run_git(repo, "checkout", "-q", "-b", "work")
    _run_git(repo, "branch", "-D", "develop")  # only origin/develop remains
    current = [Violation("PS-214", "pyproject.toml", "detail")]
    # Act
    escalate_new_violations(
        repo, current, ("PS-214",), lambda base: [], baseline_ref="develop"
    )
    # Assert — resolved via the origin/<ref> fallback, not a silent no-op
    assert current[0].severity_override == "E"


# EOF
