"""Unit tests for the branch-protection gate's REFUSAL MESSAGE.

Refusing is already correct — deleting the legacy workflows without
reconciling protection permanently deadlocks every PR in the repo. What was
missing is the remedy. Measured on scitex-hub, 2026-07-28: protection
required the BARE names (`pytest-matrix-on-ubuntu-py3.11`, `audit`) while a
`workflow_call` caller emits the PREFIXED form
(`pytest-matrix / pytest-matrix-on-ubuntu-py3.11`), and the message left the
operator to derive that mapping by hand.

No mocks (STX-NM002): the gate is driven through `apply`'s existing
`required_contexts_lookup` / `owner_repo_lookup` VALUE seams against a real
`tmp_path` repo, and the renderer is a pure function read directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._ecosystem.ci_template import (
    BranchProtectionGateError,
    apply,
    emitted_job_names,
    render_gate_failure,
    suggest_new_context,
)

#: The exact scitex-hub shape: bare legacy contexts on BOTH branches.
_HUB_LEGACY_CONTEXTS = [
    "pytest-matrix-on-ubuntu-py3.11",
    "audit",
]


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "scitex-hub"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    (repo / ".github" / "workflows").mkdir(parents=True)
    return repo


def _gate_error(tmp_path: Path, lookup) -> BranchProtectionGateError:
    """Drive the REAL apply path until the gate refuses; return the error."""
    repo = _make_repo(tmp_path)
    with pytest.raises(BranchProtectionGateError) as excinfo:
        apply(
            repo,
            dry_run=True,
            owner_repo_lookup=lambda _d: "scitex-ai/scitex-hub",
            required_contexts_lookup=lookup,
        )
    return excinfo.value


def _gate_failure_message(tmp_path: Path) -> str:
    """The refusal text for the scitex-hub shape (stale contexts, both branches)."""
    return str(
        _gate_error(tmp_path, lambda _o, _b: list(_HUB_LEGACY_CONTEXTS))
    )


# --------------------------------------------------------------------------- #
# Old names, new names, both branches — the three things the operator needs
# --------------------------------------------------------------------------- #


def test_refusal_names_the_old_contexts(tmp_path):
    # Arrange
    message = _gate_failure_message(tmp_path)
    # Act
    present = [old for old in _HUB_LEGACY_CONTEXTS if old in message]
    # Assert
    assert present == _HUB_LEGACY_CONTEXTS


def test_refusal_names_the_new_prefixed_contexts(tmp_path):
    # Arrange
    message = _gate_failure_message(tmp_path)
    expected_new = [
        "pytest-matrix / pytest-matrix-on-ubuntu-py3.11",
        "quality-audit / audit",
    ]
    # Act
    present = [new for new in expected_new if new in message]
    # Assert
    assert present == expected_new


def test_refusal_names_both_affected_branches(tmp_path):
    # Both develop and main carry the stale contexts in this fixture; a
    # message that named only one would leave half the deadlock in place.
    # Arrange
    message = _gate_failure_message(tmp_path)
    # Act
    named = [br for br in ("develop", "main") if br in message]
    # Assert
    assert named == ["develop", "main"]


def test_refusal_states_that_protection_must_be_updated_first(tmp_path):
    # Arrange
    message = _gate_failure_message(tmp_path)
    # Act
    says_before = "BEFORE" in message
    # Assert
    assert says_before


def test_refusal_carries_a_concrete_gh_command(tmp_path):
    # Arrange
    message = _gate_failure_message(tmp_path)
    # Act
    has_command = (
        "gh api -X PATCH repos/scitex-ai/scitex-hub/branches/develop/protection"
        in message
    )
    # Assert
    assert has_command


def test_refusal_does_not_advertise_the_skip_flag_as_the_fix(tmp_path):
    # `--skip-required-check-gate` exists and is documented as dangerous. The
    # message must not read as an invitation to reach for it.
    # Arrange
    message = _gate_failure_message(tmp_path)
    # Act
    disclaimed = "`--skip-required-check-gate` is NOT the fix" in message
    # Assert
    assert disclaimed


# --------------------------------------------------------------------------- #
# The old -> new correspondence itself
# --------------------------------------------------------------------------- #


def test_suggest_new_context_maps_bare_name_to_prefixed_form():
    # Arrange
    emitted = emitted_job_names(["3.11"])
    # Act
    suggestion = suggest_new_context("pytest-matrix-on-ubuntu-py3.11", emitted)
    # Assert
    assert suggestion == "pytest-matrix / pytest-matrix-on-ubuntu-py3.11"


def test_suggest_new_context_returns_none_for_a_retired_check():
    # Arrange
    emitted = emitted_job_names(["3.11"])
    # Act
    suggestion = suggest_new_context("newb-docs-quality", emitted)
    # Assert
    assert suggestion is None


def test_retired_check_is_reported_as_remove_from_protection():
    # A context nothing emits cannot be RENAMED — it must be dropped, and the
    # worksheet must say so instead of leaving a blank.
    # Arrange
    missing = {"develop": ["newb-docs-quality"]}
    # Act
    message = render_gate_failure(missing, emitted_job_names(["3.11"]))
    # Assert
    assert "RETIRED" in message


def test_render_gate_failure_lists_the_full_emitted_set():
    # Arrange
    emitted = emitted_job_names(["3.11"])
    # Act
    message = render_gate_failure({"main": ["audit"]}, emitted)
    # Assert
    assert all(name in message for name in emitted)


def test_gate_error_retains_structured_missing_map(tmp_path):
    # The rendered text is for humans; callers keep the data.
    # Arrange
    lookup = lambda _o, br: (["audit"] if br == "develop" else [])
    # Act
    error = _gate_error(tmp_path, lookup)
    # Assert
    assert error.missing == {"develop": ["audit"]}


# EOF
