"""Tests for `_github_state.py` (PS-172 default-branch convention).

No mocks: the production code takes a `fetch_default_branch` callable,
so the test injects a real dict-backed lookup (a recorded API shape)
instead of patching the network.
"""

from __future__ import annotations

from scitex_dev._ecosystem._github_state import (
    CONVENTION_DEFAULT_BRANCH,
    UNKNOWN,
    audit_default_branches,
)

# A recorded API shape: owner/repo -> default_branch, as `gh api
# repos/<repo> --jq .default_branch` would return it.
_RECORDED = {
    "ywatanabe1989/scitex-io": "main",
    "ywatanabe1989/scitex-dev": "main",
    "ywatanabe1989/newb": "develop",
    "ywatanabe1989/scitex-config": "develop",
}


def _fetch(repo: str) -> str:
    """Real dict-backed fetcher; UNKNOWN for repos absent from the record."""
    return _RECORDED.get(repo, UNKNOWN)


def test_repo_on_main_conforms_to_convention():
    # Arrange
    repos = [("scitex-io", "ywatanabe1989/scitex-io")]
    # Act
    findings = audit_default_branches(repos, fetch_default_branch=_fetch)
    # Assert
    assert findings[0].ok is True


def test_repo_on_develop_deviates_from_convention():
    # Arrange
    repos = [("newb", "ywatanabe1989/newb")]
    # Act
    findings = audit_default_branches(repos, fetch_default_branch=_fetch)
    # Assert
    assert findings[0].deviates is True


def test_unreachable_repo_is_unknown_not_deviating():
    # Arrange
    repos = [("ghost", "ywatanabe1989/does-not-exist")]
    # Act
    findings = audit_default_branches(repos, fetch_default_branch=_fetch)
    # Assert
    assert findings[0].unknown is True


def test_convention_default_branch_is_main():
    # Arrange
    repos = [("scitex-dev", "ywatanabe1989/scitex-dev")]
    # Act
    findings = audit_default_branches(repos, fetch_default_branch=_fetch)
    # Assert
    assert findings[0].expected == CONVENTION_DEFAULT_BRANCH == "main"


def test_findings_preserve_input_order():
    # Arrange
    repos = [
        ("newb", "ywatanabe1989/newb"),
        ("scitex-io", "ywatanabe1989/scitex-io"),
    ]
    # Act
    findings = audit_default_branches(repos, fetch_default_branch=_fetch)
    # Assert
    assert [f.package for f in findings] == ["newb", "scitex-io"]
