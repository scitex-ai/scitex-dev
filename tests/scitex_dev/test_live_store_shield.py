#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the session live-store shield (tests/conftest.py).

The shield exists because full-suite pytest runs with the session's ambient
environment mass-deleted the fleet's live scitex-cards store
(~/.scitex/cards/cards.db, incident 2026-07-21). These tests prove that:

1. every store-steering env var points into the per-session tmp dir while
   tests run (never at a live path);
2. the leak assertion actually FIRES on a simulated leak — constructed from
   a saved copy of the pre-shield environment, never by unshielding the
   running session.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests import conftest as shield


def test_every_store_path_var_points_into_session_tmp(_shield_live_card_store):
    """Each path-bearing store var is force-set inside the session tmp dir."""
    # Arrange
    tmp_dir = Path(_shield_live_card_store.tmp_dir).resolve()
    live_paths = _shield_live_card_store.live_paths
    # Act: collect every var whose value is missing, escapes tmp, or is live.
    violations = [
        f"{var}={os.environ.get(var)!r}"
        for var in shield._STORE_PATH_ENV
        if not os.environ.get(var)
        or not Path(os.environ[var]).resolve().is_relative_to(tmp_dir)
        or Path(os.environ[var]).resolve() in live_paths
    ]
    # Assert
    assert not violations, f"store vars escaped the shield: {violations}"


def test_scitex_dir_is_relocated_into_session_tmp(_shield_live_card_store):
    """$SCITEX_DIR (the ~/.scitex relocation lever) is repointed too."""
    # Arrange
    tmp_dir = Path(_shield_live_card_store.tmp_dir).resolve()
    # Act
    value = os.environ.get("SCITEX_DIR")
    # Assert
    assert value is not None and Path(value).resolve().is_relative_to(tmp_dir)


def test_backend_selectors_are_forced_to_local_values(_shield_live_card_store):
    """Backend/dual-write selectors carry the forced local-file values."""
    # Arrange
    expected = dict(shield._STORE_VALUE_ENV)
    # Act
    actual = {var: os.environ.get(var) for var in expected}
    # Assert
    assert actual == expected


def test_remote_hub_endpoint_vars_are_unset(_shield_live_card_store):
    """Remote-hub URL/token vars are removed (local backend selected)."""
    # Arrange
    hub_vars = shield._STORE_UNSET_ENV
    # Act
    leaked = [var for var in hub_vars if var in os.environ]
    # Assert
    assert not leaked, f"hub endpoint vars survived the shield: {leaked}"


def test_tmp_tasks_yaml_is_an_empty_valid_store(_shield_live_card_store):
    """The repointed tasks.yaml exists and carries a top-level tasks key."""
    # Arrange
    tasks_yaml = Path(os.environ["SCITEX_TODO_TASKS"])
    # Act
    content = tasks_yaml.read_text(encoding="utf-8")
    # Assert
    assert content.startswith("tasks:")


def test_resolved_store_target_resolves_inside_session_tmp(
    _shield_live_card_store,
):
    """The path a writer would actually hit resolves inside the tmp dir."""
    # Arrange
    tmp_dir = Path(_shield_live_card_store.tmp_dir).resolve()
    # Act
    resolved = shield._resolved_store_target(os.environ).resolve()
    # Assert
    assert resolved.is_relative_to(tmp_dir)


def test_assert_shielded_accepts_the_shielded_target(_shield_live_card_store):
    """The defense-in-depth assertion passes on the shielded store target."""
    # Arrange
    resolved = shield._resolved_store_target(os.environ)
    # Act: must not raise on a shielded target.
    outcome = shield._assert_shielded(
        resolved, _shield_live_card_store.live_paths
    )
    # Assert
    assert outcome is None


def test_leak_assertion_fires_on_home_default_cards_db(_shield_live_card_store):
    """A resolution falling back to ~/.scitex/cards/cards.db must trip."""
    # Arrange
    home = Path.home()
    live = shield._live_store_paths({}, home)
    # Act
    leaked = home / ".scitex" / "cards" / "cards.db"
    # Assert
    with pytest.raises(RuntimeError, match="LIVE"):
        shield._assert_shielded(leaked, live)


def test_leak_assertion_fires_on_home_default_tasks_yaml(
    _shield_live_card_store,
):
    """A resolution falling back to ~/.scitex/todo/tasks.yaml must trip."""
    # Arrange
    home = Path.home()
    live = shield._live_store_paths({}, home)
    # Act
    leaked = home / ".scitex" / "todo" / "tasks.yaml"
    # Assert
    with pytest.raises(RuntimeError, match="LIVE"):
        shield._assert_shielded(leaked, live)


def test_leak_assertion_fires_on_saved_ambient_env(_shield_live_card_store):
    """A leak simulated from a saved copy of the ORIGINAL env must trip.

    Uses the pre-shield snapshot the session fixture captured (plus an
    explicit ambient-style value), never the live process env — the running
    session stays shielded throughout.
    """
    # Arrange
    home = Path.home()
    original = {
        var: value
        for var, value in _shield_live_card_store.saved_env.items()
        if value is not None
    }
    original.setdefault(
        "SCITEX_CARDS_DB", str(home / ".scitex" / "cards" / "cards.db")
    )
    live = shield._live_store_paths(original, home)
    # Act
    leaked = Path(original["SCITEX_CARDS_DB"]).expanduser()
    # Assert
    with pytest.raises(RuntimeError, match="LIVE"):
        shield._assert_shielded(leaked, live)


def test_saved_env_snapshot_covers_every_shielded_var(_shield_live_card_store):
    """Teardown-restore snapshot covers the whole shielded surface."""
    # Arrange
    expected = set(shield._SHIELDED_ENV_VARS)
    # Act
    snapshot = set(_shield_live_card_store.saved_env)
    # Assert
    assert snapshot == expected


# EOF
