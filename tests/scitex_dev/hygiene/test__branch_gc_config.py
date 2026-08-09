#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DEFAULT OFF, and FAIL CLOSED — pinned one route at a time.

Every test passes an explicit ``home=`` so none of them can accidentally
read the invoking operator's real ``~/.scitex/dev/config.yaml``. A
DEFAULT-OFF test that depends on the machine it runs on proves nothing.
"""

from __future__ import annotations

import pytest

from scitex_dev.hygiene._branch_gc_config import (
    CleanupConfig,
    load_branch_cleanup_config,
)
from scitex_dev.hygiene._branch_gc_model import HARD_MIN_AGE_DAYS


def _write(root, body: str) -> None:
    target = root / ".scitex" / "dev" / "config.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


_ARMED = "cleanup:\n  branches:\n    enabled: true\n"


# --------------------------------------------------------------------------
# Gate 1 — the dataclass itself is OFF before any file is read.
# --------------------------------------------------------------------------


def test_dataclass_default_is_disabled():
    """A CleanupConfig built with no arguments deletes nothing."""
    # Arrange
    # Act
    config = CleanupConfig()
    # Assert
    assert config.enabled is False


# --------------------------------------------------------------------------
# Gate 2 — fail CLOSED on every route to doubt.
# --------------------------------------------------------------------------


def test_no_config_at_all_is_disabled(tmp_path):
    """NO CONFIG PRESENT: the primitive does nothing. (Required property 1a.)"""
    # Arrange
    repo = tmp_path / "repo"
    repo.mkdir()
    # Act
    config = load_branch_cleanup_config(repo, home=tmp_path / "home")
    # Assert
    assert config.enabled is False


def test_no_config_at_all_states_a_reason(tmp_path):
    """OFF is never silent: the absent file is named."""
    # Arrange
    repo = tmp_path / "repo"
    repo.mkdir()
    # Act
    config = load_branch_cleanup_config(repo, home=tmp_path / "home")
    # Assert
    assert "no config at" in (config.error or "")


def test_config_present_but_cleanup_key_absent_is_disabled(tmp_path):
    """CONFIG PRESENT, KEY ABSENT: still nothing. (Required property 1b.)"""
    # Arrange
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write(repo, "project-type:\n  - pip\n")
    _write(home, "project-type:\n  - pip\n")
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.enabled is False


def test_cleanup_block_present_but_branches_absent_is_disabled(tmp_path):
    """A sibling sweep being configured never arms this one."""
    # Arrange
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write(repo, "cleanup:\n  worktrees:\n    enabled: true\n")
    _write(home, _ARMED)
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.enabled is False


@pytest.mark.parametrize("literal", ['"true"', '"yes"', "1", "[true]", "True_"])
def test_non_boolean_true_does_not_arm(tmp_path, literal):
    """`enabled` is armed by the YAML boolean alone — never a lookalike.

    The check is ``is True`` against the PARSED value, so what counts is
    the YAML type, not the spelling. Measured against PyYAML: the quoted
    ``"true"`` and ``"yes"`` are STRINGS, ``1`` is an INT, ``[true]`` is a
    LIST — none of them arm anything. Bare ``yes`` and bare ``on`` are
    genuine YAML 1.1 booleans and DO arm it, which is correct and is
    pinned by ``test_bare_yes_is_a_real_yaml_boolean_and_arms``.
    """
    # Arrange
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write(repo, f"cleanup:\n  branches:\n    enabled: {literal}\n")
    _write(home, _ARMED)
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.enabled is False


def test_bare_yes_is_a_real_yaml_boolean_and_arms(tmp_path):
    """MEASURED, not assumed: PyYAML resolves bare `yes` to True.

    Documented rather than defended against. The gate's contract is "the
    parsed value must BE the boolean", and `yes` is that boolean under
    YAML 1.1 — so accepting it is the contract working, not a leak. What
    the gate rejects is a value that merely LOOKS like one.
    """
    # Arrange
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write(repo, "cleanup:\n  branches:\n    enabled: yes\n")
    _write(home, _ARMED)
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.enabled is True


def test_malformed_yaml_is_disabled(tmp_path):
    """Unparseable config fails CLOSED — the opposite of gate/_config.py."""
    # Arrange
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write(repo, "cleanup:\n  branches:\n   - enabled: [true\n")
    _write(home, _ARMED)
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.enabled is False


def test_cleanup_not_a_mapping_is_disabled(tmp_path):
    """`cleanup: true` is a shape error, and a shape error means OFF."""
    # Arrange
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write(repo, "cleanup: true\n")
    _write(home, _ARMED)
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.enabled is False


# --------------------------------------------------------------------------
# The AND, not OR, between the two surfaces.
# --------------------------------------------------------------------------


def test_repo_armed_but_user_config_absent_is_disabled(tmp_path):
    """The fleet-wide kill switch is a REQUIREMENT, not an override."""
    # Arrange
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write(repo, _ARMED)
    home.mkdir(parents=True, exist_ok=True)
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.enabled is False


def test_user_armed_but_repo_config_absent_is_disabled(tmp_path):
    """A fleet-wide opt-in never arms a repo that did not opt in itself."""
    # Arrange
    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "home"
    _write(home, _ARMED)
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.enabled is False


def test_both_surfaces_armed_is_enabled(tmp_path):
    """POSITIVE CONTROL: with both files armed, the loader does say True.

    Without this, every OFF assertion above would also pass on a loader
    that is hard-wired to return False.
    """
    # Arrange
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write(repo, _ARMED)
    _write(home, _ARMED)
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.enabled is True


# --------------------------------------------------------------------------
# The age floor cannot be lowered by configuration.
# --------------------------------------------------------------------------


def test_configured_age_below_hard_floor_is_clamped_up(tmp_path):
    """min-age-days: 1 is CLAMPED to the hard floor, never honoured."""
    # Arrange
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write(repo, _ARMED + "    min-age-days: 1\n")
    _write(home, _ARMED)
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.min_age_days == HARD_MIN_AGE_DAYS


def test_configured_age_above_hard_floor_is_honoured(tmp_path):
    """Config may make the sweep MORE conservative."""
    # Arrange
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write(repo, _ARMED + "    min-age-days: 90\n")
    _write(home, _ARMED)
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.min_age_days == 90.0


def test_protect_globs_are_read_from_repo_config(tmp_path):
    """Extra protect globs are additive to the built-in shield."""
    # Arrange
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write(repo, _ARMED + '    protect:\n      - "relocation/*"\n')
    _write(home, _ARMED)
    # Act
    config = load_branch_cleanup_config(repo, home=home)
    # Assert
    assert config.protect == ("relocation/*",)


# EOF
