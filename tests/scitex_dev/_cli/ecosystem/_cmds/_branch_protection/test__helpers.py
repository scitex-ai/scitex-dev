"""Behavioural tests for `scitex-dev ecosystem set-branch-protection` /
`unset-branch-protection`.

No mocks. The gh-api + owner-repo boundary is replaced via direct
attribute assignment + try/finally restoration (a real injection seam),
NOT ``unittest.mock`` / ``pytest-mock`` / ``monkeypatch.setattr`` —
PA-306 forbids mock-shaped tests. Same pattern as install-gate and
sync-status tests use for their own external boundaries.

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
# Real injection seam — replaces the module-level gh-api callable + the
# owner-repo resolver for the duration of one test. Restore via
# try/finally in the fixture (no monkeypatch, no mock).
# ---------------------------------------------------------------------------


class _Seam:
    """Records (method, endpoint, body) calls; serves canned responses."""

    def __init__(self, owner_repo: str = "ywatanabe1989/scitex-dev"):
        self.canned: List[Tuple[int, str]] = []
        self.calls: List[Tuple[str, str, object]] = []
        self.owner_repo = owner_repo

    def __call__(self, method: str, endpoint: str, body=None):
        self.calls.append((method, endpoint, body))
        return self.canned.pop(0)


def _resolve_seam_owner_repo(_distribution: str) -> str:
    """Stand-in for the registry resolver; reads from the active seam."""
    return _ACTIVE_SEAM.owner_repo if _ACTIVE_SEAM is not None else None


# Module-level handle so the resolver stand-in can read the active seam.
_ACTIVE_SEAM: "_Seam | None" = None


@pytest.fixture
def gh_seam():
    """Yield a fresh seam; restore originals on teardown."""
    global _ACTIVE_SEAM
    seam = _Seam()
    orig_gh = _branch_protection._gh_api
    orig_resolve = _branch_protection._resolve_owner_repo
    _branch_protection._gh_api = seam
    _branch_protection._resolve_owner_repo = _resolve_seam_owner_repo
    _ACTIVE_SEAM = seam
    try:
        yield seam
    finally:
        _branch_protection._gh_api = orig_gh
        _branch_protection._resolve_owner_repo = orig_resolve
        _ACTIVE_SEAM = None


def _make_group():
    """Fresh ecosystem Click group with set/unset registered."""

    @click.group()
    def root():
        pass

    _branch_protection.register(root)
    return root


# v0.17.3: contexts now come from check-runs API (not workflow names).
_BASELINE_CHECK_RUNS_JSON = (
    '{"check_runs": ['
    '{"name": "pytest-matrix-on-ubuntu-py3.11"},'
    '{"name": "pytest-matrix-on-ubuntu-py3.12"},'
    '{"name": "pytest-matrix-on-ubuntu-py3.13"},'
    '{"name": "sphinx"},'
    '{"name": "import-smoke-on-ubuntu-py3-12"},'
    '{"name": "audit"}'
    "]}"
)


def _arrange_seam_with_both_branches(seam: _Seam) -> None:
    """Canned responses for: list check-runs → develop check → develop PUT
    → main check → main PUT.
    """
    seam.canned = [
        (0, _BASELINE_CHECK_RUNS_JSON),
        (0, '{"name": "develop"}'),
        (0, "{}"),
        (0, '{"name": "main"}'),
        (0, "{}"),
    ]


def test_dry_run_does_not_invoke_gh_api_put(gh_seam):
    # Arrange
    _arrange_seam_with_both_branches(gh_seam)
    runner = CliRunner()
    # Act
    runner.invoke(_make_group(), ["set-branch-protection", "scitex-dev"])
    # Assert
    puts = [c for c in gh_seam.calls if c[0] == "PUT"]
    assert len(puts) == 0


def test_execute_emits_put_per_existing_branch(gh_seam):
    # Arrange
    _arrange_seam_with_both_branches(gh_seam)
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        ["set-branch-protection", "scitex-dev", "--execute"],
    )
    # Assert
    puts = [c for c in gh_seam.calls if c[0] == "PUT"]
    assert len(puts) == 2


def test_develop_put_uses_enforce_admins_true(gh_seam):
    # Arrange
    _arrange_seam_with_both_branches(gh_seam)
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


def test_main_put_uses_enforce_admins_false(gh_seam):
    # Arrange
    _arrange_seam_with_both_branches(gh_seam)
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


def test_policy_uses_strict_false_per_lead_doctrine(gh_seam):
    # Arrange
    gh_seam.canned = [
        (0, _BASELINE_CHECK_RUNS_JSON),
        (0, '{"name": "develop"}'),
        (0, "{}"),
    ]
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


def test_policy_required_linear_history_true(gh_seam):
    # Arrange
    gh_seam.canned = [
        (0, _BASELINE_CHECK_RUNS_JSON),
        (0, '{"name": "develop"}'),
        (0, "{}"),
    ]
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


def test_policy_required_pull_request_reviews_omitted(gh_seam):
    # Arrange
    gh_seam.canned = [
        (0, _BASELINE_CHECK_RUNS_JSON),
        (0, '{"name": "develop"}'),
        (0, "{}"),
    ]
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


def test_policy_allow_force_pushes_false(gh_seam):
    # Arrange
    gh_seam.canned = [
        (0, _BASELINE_CHECK_RUNS_JSON),
        (0, '{"name": "develop"}'),
        (0, "{}"),
    ]
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


def test_required_contexts_intersected_with_published_checks(gh_seam):
    # Arrange — only 2 of the 6 ceiling contexts publish on this repo
    gh_seam.canned = [
        (0, '{"check_runs": [{"name": "sphinx"}, {"name": "audit"}]}'),
        (0, '{"name": "develop"}'),
        (0, "{}"),
    ]
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
    assert put[2]["required_status_checks"]["contexts"] == ["sphinx", "audit"]


def test_missing_develop_branch_skips_develop(gh_seam):
    # Arrange — orochi-shaped: no develop, main only
    gh_seam.owner_repo = "ywatanabe1989/scitex-orochi"
    gh_seam.canned = [
        (0, _BASELINE_CHECK_RUNS_JSON),
        (404, "Branch not found"),
        (0, '{"name": "main"}'),
        (0, "{}"),
    ]
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


def test_unknown_distribution_exits_with_error_code():
    # Arrange — replace resolver to simulate "not in ECOSYSTEM"
    orig_resolve = _branch_protection._resolve_owner_repo
    _branch_protection._resolve_owner_repo = lambda _d: None
    runner = CliRunner()
    try:
        # Act
        result = runner.invoke(
            _make_group(),
            ["set-branch-protection", "nonexistent-distribution"],
        )
    finally:
        _branch_protection._resolve_owner_repo = orig_resolve
    # Assert
    assert result.exit_code == 2


def test_unset_dry_run_does_not_invoke_gh_api_delete(gh_seam):
    # Arrange
    gh_seam.canned = [
        (0, '{"name": "develop"}'),
        (0, '{"name": "main"}'),
    ]
    runner = CliRunner()
    # Act
    runner.invoke(_make_group(), ["unset-branch-protection", "scitex-dev"])
    # Assert
    deletes = [c for c in gh_seam.calls if c[0] == "DELETE"]
    assert deletes == []


def test_unset_execute_emits_delete_per_existing_branch(gh_seam):
    # Arrange
    gh_seam.canned = [
        (0, '{"name": "develop"}'),
        (0, ""),
        (0, '{"name": "main"}'),
        (0, ""),
    ]
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        ["unset-branch-protection", "scitex-dev", "--execute"],
    )
    # Assert
    deletes = [c for c in gh_seam.calls if c[0] == "DELETE"]
    assert len(deletes) == 2


# ---------------------------------------------------------------------------
# Deletion-only baseline (Q2: fleet-wide, must NOT block CI's commit-back push)
# ---------------------------------------------------------------------------


def test_deletion_only_body_forbids_deletion():
    # Arrange
    # Act
    body = _branch_protection._deletion_only_body()
    # Assert
    assert body["allow_deletions"] is False


def test_deletion_only_body_has_no_required_status_checks():
    # Arrange
    # Act
    body = _branch_protection._deletion_only_body()
    # Assert
    assert body["required_status_checks"] is None


def test_deletion_only_body_does_not_enforce_admins():
    # Arrange — enforce_admins:false keeps CI's direct develop push working.
    # Act
    body = _branch_protection._deletion_only_body()
    # Assert
    assert body["enforce_admins"] is False


def test_deletion_only_put_sends_minimal_body(gh_seam):
    # Arrange — develop exists; deletion-only skips the check-runs lookup.
    gh_seam.canned = [
        (0, '{"name": "develop"}'),
        (0, "{}"),
    ]
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        ["set-branch-protection", "scitex-dev", "--branch", "develop",
         "--deletion-only", "--execute"],
    )
    # Assert — the PUT body carries no required_status_checks.
    develop_put = next(
        c for c in gh_seam.calls
        if c[0] == "PUT" and c[1].endswith("/branches/develop/protection")
    )
    assert develop_put[2]["required_status_checks"] is None


def test_all_distributions_returns_nonempty_list():
    # Arrange
    # Act
    dists = _branch_protection._all_distributions()
    # Assert
    assert len(dists) > 0


# ---------------------------------------------------------------------------
# Idempotent / non-downgrading baseline (skip already-protected branches)
# ---------------------------------------------------------------------------

_PROTECTED_UNDELETABLE_JSON = '{"allow_deletions": {"enabled": false}}'
_PROTECTED_DELETABLE_JSON = '{"allow_deletions": {"enabled": true}}'


def test_deletion_only_skips_already_undeletable_branch(gh_seam):
    # Arrange — develop exists, GET protection shows deletions already off.
    gh_seam.canned = [
        (0, '{"name": "develop"}'),
        (0, _PROTECTED_UNDELETABLE_JSON),
    ]
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        ["set-branch-protection", "scitex-dev", "--branch", "develop",
         "--deletion-only", "--execute"],
    )
    # Assert — no PUT issued (the existing policy is left intact).
    puts = [c for c in gh_seam.calls if c[0] == "PUT"]
    assert len(puts) == 0


def test_deletion_only_applies_when_branch_deletable(gh_seam):
    # Arrange — develop exists, GET shows deletions currently ALLOWED.
    gh_seam.canned = [
        (0, '{"name": "develop"}'),
        (0, _PROTECTED_DELETABLE_JSON),
        (0, "{}"),
    ]
    runner = CliRunner()
    # Act
    runner.invoke(
        _make_group(),
        ["set-branch-protection", "scitex-dev", "--branch", "develop",
         "--deletion-only", "--execute"],
    )
    # Assert — baseline IS applied (one PUT).
    puts = [c for c in gh_seam.calls if c[0] == "PUT"]
    assert len(puts) == 1
