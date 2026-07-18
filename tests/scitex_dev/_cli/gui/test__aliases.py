#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Phase W aliases that keep the pre-`gui` dashboard paths working.

§12 clears a legacy gui-adjacent leaf only when it is hidden AND
carries `_deprecated_alias` metadata, so these tests pin both halves —
the audit contract and the behaviour the users actually depend on.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev._cli.audit._summary._gui_group import REQUIRED_GUI_VERBS


@pytest.fixture()
def gui_group():
    return main.commands["gui"]


@pytest.fixture()
def ecosystem_group():
    return main.commands["ecosystem"]


@pytest.mark.parametrize("verb", REQUIRED_GUI_VERBS)
def test_gui_group_exposes_every_required_verb(gui_group, verb):
    # Arrange
    registered = gui_group.commands
    # Act
    present = verb in registered
    # Assert
    assert present


def test_gui_group_is_not_hidden(gui_group):
    # Arrange
    group = gui_group
    # Act
    hidden = bool(getattr(group, "hidden", False))
    # Assert
    assert hidden is False


@pytest.mark.parametrize("legacy", ["dashboard", "start-dashboard"])
def test_legacy_ecosystem_leaf_is_hidden(ecosystem_group, legacy):
    # Arrange
    cmd = ecosystem_group.commands[legacy]
    # Act
    hidden = bool(getattr(cmd, "hidden", False))
    # Assert
    assert hidden is True


@pytest.mark.parametrize("legacy", ["dashboard", "start-dashboard"])
def test_legacy_ecosystem_leaf_carries_alias_metadata(ecosystem_group, legacy):
    # Arrange
    cmd = ecosystem_group.commands[legacy]
    # Act
    meta = getattr(cmd, "_deprecated_alias", None)
    # Assert
    assert meta is not None


@pytest.mark.parametrize(
    "legacy,target",
    [("dashboard", "gui"), ("start-dashboard", "gui open")],
)
def test_legacy_ecosystem_leaf_points_at_the_canonical_target(
    ecosystem_group, legacy, target
):
    # Arrange
    cmd = ecosystem_group.commands[legacy]
    # Act
    meta = cmd._deprecated_alias
    # Assert
    assert meta["target"] == target


def test_gui_start_alias_forwards_to_watch(gui_group):
    # Arrange
    cmd = gui_group.commands["start"]
    # Act
    meta = cmd._deprecated_alias
    # Assert
    assert meta["target"] == "gui watch"


@pytest.mark.parametrize(
    "argv",
    [
        ["ecosystem", "start-dashboard", "--dry-run"],
        ["ecosystem", "dashboard", "start", "--dry-run"],
        ["ecosystem", "dashboard", "start-tui", "--dry-run"],
    ],
)
def test_legacy_path_still_runs(argv):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, argv)
    # Assert
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["ecosystem", "start-dashboard", "--dry-run"], "would ensure"),
        (["ecosystem", "dashboard", "start", "--dry-run"], "would render"),
        (["ecosystem", "dashboard", "start-tui", "--dry-run"], "would launch TUI"),
    ],
)
def test_legacy_path_lands_on_the_new_command(argv, expected):
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, argv)
    # Assert
    assert expected in result.output


def test_every_pre_migration_capability_is_still_reachable(gui_group):
    """list / start / start-tui / export all still resolve under `gui`."""
    # Arrange
    expected = {"list", "start", "start-tui", "export", "watch"}
    # Act
    registered = set(gui_group.commands)
    # Assert
    assert expected <= registered


# EOF
