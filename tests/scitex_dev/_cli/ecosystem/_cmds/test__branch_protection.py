"""Behavioural tests for `scitex-dev ecosystem set-branch-protection` /
`unset-branch-protection`.

Each test drives the actual Click command through ``CliRunner`` and
intercepts the ``gh api`` subprocess boundary via a per-test record/replay
seam. The seam is a real injection point (replacing
``_branch_protection._gh_api`` for the test's lifetime), not a unittest
mock — same pattern the install-gate / sync-status tests use for the
``gh`` boundary.

Each test is AAA-marked and asserts a single observable property
(STX-TQ002 / STX-TQ007).
"""

from __future__ import annotations

from typing import List, Tuple

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem._cmds import _branch_protection


# ---------------------------------------------------------------------------
# Subprocess seam — replaces _branch_protection._gh_api for the duration
# of one test. The replacement records (method, endpoint, body) calls in
# the order they arrived and serves canned responses from a FIFO.
# ---------------------------------------------------------------------------


class _Seam:
    """Recording / replay seam for the gh-api boundary."""

    def __init__(self, canned: List[Tuple[int, str]]):
        self.canned = list(canned)
        self.calls: List[Tuple[str, str, object]] = []

    def __call__(self, method: str, endpoint: str, body=None):
        self.calls.append((method, endpoint, body))
        return self.canned.pop(0)


@pytest.fixture
def gh_seam(monkeypatch):
    seam = _Seam(canned=[])
    monkeypatch.setattr(_branch_protection, "_gh_api", seam)
    yield seam


def _make_group():
    """Return a fresh ecosystem Click group with set/unset registered."""

    @click.group()
    def root():
        pass

    _branch_protection.register(root)
    return root


_BASELINE_WORKFLOWS_JSON = (
    '{"workflows": ['
    '{"name": "tests", "state": "active"},'
    '{"name": "docs", "state": "active"},'
    '{"name": "import-smoke", "state": "active"},'
    '{"name": "quality", "state": "active"}'
    "]}"
)


def _arrange_seam_with_both_branches(seam) -> None:
    """Canned responses for: list workflows → develop check → develop PUT
    → main check → main PUT.
    """
    seam.canned = [
        (0, _BASELINE_WORKFLOWS_JSON),
        (0, '{"name": "develop"}'),
        (0, '{}'),
        (0, '{"name": "main"}'),
        (0, '{}'),
    ]


def test_dry_run_does_not_invoke_gh_api_put(gh_seam, monkeypatch):
    # Arrange
    _arrange_seam_with_both_branches(gh_seam)
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: "ywatanabe1989/scitex-dev",
    )
    runner = CliRunner()
    # Act
    runner.invoke(_make_group(), ["set-branch-protection", "scitex-dev"])
    # Assert
    puts = [c for c in gh_seam.calls if c[0] == "PUT"]
    assert len(puts) == 0


def test_execute_emits_put_per_existing_branch(gh_seam, monkeypatch):
    # Arrange
    _arrange_seam_with_both_branches(gh_seam)
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: "ywatanabe1989/scitex-dev",
    )
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        ["set-branch-protection", "scitex-dev", "--execute"],
    )
    # Assert
    puts = [c for c in gh_seam.calls if c[0] == "PUT"]
    assert len(puts) == 2


def test_develop_put_uses_enforce_admins_true(gh_seam, monkeypatch):
    # Arrange
    _arrange_seam_with_both_branches(gh_seam)
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: "ywatanabe1989/scitex-dev",
    )
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        ["set-branch-protection", "scitex-dev", "--execute"],
    )
    # Assert
    develop_put = next(
        c for c in gh_seam.calls
        if c[0] == "PUT" and c[1].endswith("/branches/develop/protection")
    )
    assert develop_put[2]["enforce_admins"] is True


def test_main_put_uses_enforce_admins_false(gh_seam, monkeypatch):
    # Arrange
    _arrange_seam_with_both_branches(gh_seam)
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: "ywatanabe1989/scitex-dev",
    )
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        ["set-branch-protection", "scitex-dev", "--execute"],
    )
    # Assert
    main_put = next(
        c for c in gh_seam.calls
        if c[0] == "PUT" and c[1].endswith("/branches/main/protection")
    )
    assert main_put[2]["enforce_admins"] is False


def test_policy_uses_strict_false_per_lead_doctrine(gh_seam, monkeypatch):
    # Arrange
    gh_seam.canned = [
        (0, _BASELINE_WORKFLOWS_JSON),
        (0, '{"name": "develop"}'),
        (0, '{}'),
    ]
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: "ywatanabe1989/scitex-dev",
    )
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        [
            "set-branch-protection",
            "scitex-dev",
            "--branch",
            "develop",
            "--execute",
        ],
    )
    # Assert
    put = next(c for c in gh_seam.calls if c[0] == "PUT")
    assert put[2]["required_status_checks"]["strict"] is False


def test_policy_required_linear_history_true(gh_seam, monkeypatch):
    # Arrange
    gh_seam.canned = [
        (0, _BASELINE_WORKFLOWS_JSON),
        (0, '{"name": "develop"}'),
        (0, '{}'),
    ]
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: "ywatanabe1989/scitex-dev",
    )
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        [
            "set-branch-protection",
            "scitex-dev",
            "--branch",
            "develop",
            "--execute",
        ],
    )
    # Assert
    put = next(c for c in gh_seam.calls if c[0] == "PUT")
    assert put[2]["required_linear_history"] is True


def test_policy_required_pull_request_reviews_omitted(gh_seam, monkeypatch):
    # Arrange
    gh_seam.canned = [
        (0, _BASELINE_WORKFLOWS_JSON),
        (0, '{"name": "develop"}'),
        (0, '{}'),
    ]
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: "ywatanabe1989/scitex-dev",
    )
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        [
            "set-branch-protection",
            "scitex-dev",
            "--branch",
            "develop",
            "--execute",
        ],
    )
    # Assert
    put = next(c for c in gh_seam.calls if c[0] == "PUT")
    assert put[2]["required_pull_request_reviews"] is None


def test_policy_allow_force_pushes_false(gh_seam, monkeypatch):
    # Arrange
    gh_seam.canned = [
        (0, _BASELINE_WORKFLOWS_JSON),
        (0, '{"name": "develop"}'),
        (0, '{}'),
    ]
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: "ywatanabe1989/scitex-dev",
    )
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        [
            "set-branch-protection",
            "scitex-dev",
            "--branch",
            "develop",
            "--execute",
        ],
    )
    # Assert
    put = next(c for c in gh_seam.calls if c[0] == "PUT")
    assert put[2]["allow_force_pushes"] is False


def test_missing_develop_branch_skips_develop(gh_seam, monkeypatch):
    # Arrange — orochi-shaped: no develop, main only
    gh_seam.canned = [
        (0, _BASELINE_WORKFLOWS_JSON),
        (404, "Branch not found"),
        (0, '{"name": "main"}'),
        (0, '{}'),
    ]
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: "ywatanabe1989/scitex-orochi",
    )
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        ["set-branch-protection", "scitex-orochi", "--execute"],
    )
    # Assert
    develop_puts = [
        c for c in gh_seam.calls
        if c[0] == "PUT" and c[1].endswith("/branches/develop/protection")
    ]
    assert develop_puts == []


def test_unknown_distribution_exits_with_error_code(gh_seam, monkeypatch):
    # Arrange
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: None,
    )
    runner = CliRunner()
    # Act
    result = runner.invoke(
        _make_group(),
        ["set-branch-protection", "nonexistent-distribution"],
    )
    # Assert
    assert result.exit_code == 2


def test_unset_dry_run_does_not_invoke_gh_api_delete(gh_seam, monkeypatch):
    # Arrange
    gh_seam.canned = [
        (0, '{"name": "develop"}'),
        (0, '{"name": "main"}'),
    ]
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: "ywatanabe1989/scitex-dev",
    )
    runner = CliRunner()
    # Act
    runner.invoke(_make_group(), ["unset-branch-protection", "scitex-dev"])
    # Assert
    deletes = [c for c in gh_seam.calls if c[0] == "DELETE"]
    assert deletes == []


def test_unset_execute_emits_delete_per_existing_branch(gh_seam, monkeypatch):
    # Arrange
    gh_seam.canned = [
        (0, '{"name": "develop"}'),
        (0, ''),
        (0, '{"name": "main"}'),
        (0, ''),
    ]
    monkeypatch.setattr(
        _branch_protection,
        "_resolve_owner_repo",
        lambda d: "ywatanabe1989/scitex-dev",
    )
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        ["unset-branch-protection", "scitex-dev", "--execute"],
    )
    # Assert
    deletes = [c for c in gh_seam.calls if c[0] == "DELETE"]
    assert len(deletes) == 2
