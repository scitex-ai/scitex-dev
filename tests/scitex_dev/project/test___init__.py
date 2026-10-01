#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project selection contracts against real isolated configuration/state."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scitex_dev.project import (
    ALL_PROJECTS,
    active_project_file,
    clear_active_project,
    resolve_project,
    set_active_project,
    validate_ref,
)


@pytest.fixture
def owned_project_state(tmp_path):
    """Own selection configuration without replacing HOME or implementation."""
    keys = ("SCITEX_DIR", "SCITEX_PROJECT")
    saved = {key: os.environ.get(key) for key in keys}
    home = os.environ.get("HOME")
    os.environ["SCITEX_DIR"] = str(tmp_path)
    os.environ.pop("SCITEX_PROJECT", None)
    try:
        yield SimpleNamespace(root=tmp_path, home=home)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_owner_slash_name_is_accepted():
    # Arrange
    ref = "scitex-04/dotfiles"
    # Act
    validated = validate_ref(ref)
    # Assert
    assert validated == ref


def test_all_projects_literal_is_accepted():
    # Arrange
    ref = "all"
    # Act
    validated = validate_ref(ref)
    # Assert
    assert validated == ALL_PROJECTS


def test_bare_project_name_is_rejected():
    # Arrange
    ref = "dotfiles"
    # Act
    # Assert
    with pytest.raises(ValueError):
        validate_ref(ref)


def test_project_owner_traversal_is_rejected():
    # Arrange
    ref = "../evil/x"
    # Act
    # Assert
    with pytest.raises(ValueError):
        validate_ref(ref)


def test_explicit_selection_wins_over_environment_and_file(owned_project_state):
    # Arrange
    os.environ["SCITEX_PROJECT"] = "env/proj"
    set_active_project("file/proj")
    # Act
    selected = resolve_project("arg/proj")
    # Assert
    assert selected == "arg/proj"


def test_environment_selection_wins_over_persisted_file(owned_project_state):
    # Arrange
    os.environ["SCITEX_PROJECT"] = "env/proj"
    set_active_project("file/proj")
    # Act
    selected = resolve_project()
    # Assert
    assert selected == "env/proj"


def test_file_selection_is_used_without_environment(owned_project_state):
    # Arrange
    set_active_project("file/proj")
    # Act
    selected = resolve_project()
    # Assert
    assert selected == "file/proj"


def test_missing_selection_resolves_to_none(owned_project_state):
    # Arrange
    resolver = resolve_project
    # Act
    selected = resolver()
    # Assert
    assert selected is None


def test_persisting_selection_returns_its_validated_ref(owned_project_state):
    # Arrange
    ref = "scitex-04/dotfiles"
    # Act
    selected = set_active_project(ref)
    # Assert
    assert selected == ref


def test_persisted_selection_roundtrips_through_resolver(owned_project_state):
    # Arrange
    set_active_project("scitex-04/dotfiles")
    # Act
    selected = resolve_project()
    # Assert
    assert selected == "scitex-04/dotfiles"


def test_first_clear_reports_removed_selection(owned_project_state):
    # Arrange
    set_active_project("a/b")
    # Act
    cleared = clear_active_project()
    # Assert
    assert cleared is True


def test_cleared_selection_resolves_to_none(owned_project_state):
    # Arrange
    set_active_project("a/b")
    clear_active_project()
    # Act
    selected = resolve_project()
    # Assert
    assert selected is None


def test_second_clear_reports_no_selection(owned_project_state):
    # Arrange
    set_active_project("a/b")
    clear_active_project()
    # Act
    cleared = clear_active_project()
    # Assert
    assert cleared is False


def test_invalid_selection_ref_is_not_persisted(owned_project_state):
    # Arrange
    ref = "bare"
    # Act
    # Assert
    with pytest.raises(ValueError):
        set_active_project(ref)


def test_rejected_selection_leaves_no_resolved_project(owned_project_state):
    # Arrange
    try:
        set_active_project("bare")
    except ValueError:
        pass
    # Act
    selected = resolve_project()
    # Assert
    assert selected is None


def test_owned_configuration_keeps_the_actual_home_environment(owned_project_state):
    # Arrange
    initial_home = owned_project_state.home
    # Act
    selected_home = os.environ.get("HOME")
    # Assert
    assert selected_home == initial_home


def test_selection_file_respects_the_supported_scitex_root(owned_project_state):
    # Arrange
    expected = owned_project_state.root / "scitex-dev" / "active_project"
    # Act
    path = active_project_file()
    # Assert
    assert path == expected


def test_persisted_bytes_are_written_only_under_owned_scitex_root(owned_project_state):
    # Arrange
    expected = owned_project_state.root / "scitex-dev" / "active_project"
    # Act
    set_active_project("owned/project")
    # Assert
    assert expected.read_text(encoding="utf-8") == "owned/project\n"


def test_clear_removes_the_owned_selection_file(owned_project_state):
    # Arrange
    expected = owned_project_state.root / "scitex-dev" / "active_project"
    set_active_project("owned/project")
    # Act
    clear_active_project()
    # Assert
    assert not expected.exists()


def test_unconfigured_root_keeps_the_existing_default_path(owned_project_state):
    # Arrange
    os.environ.pop("SCITEX_DIR")
    expected = Path(os.path.expanduser("~")) / ".scitex" / "scitex-dev" / "active_project"
    # Act
    path = active_project_file()
    # Assert
    assert path == expected


def test_empty_configured_root_keeps_the_existing_default_path(owned_project_state):
    # Arrange
    os.environ["SCITEX_DIR"] = ""
    expected = Path(os.path.expanduser("~")) / ".scitex" / "scitex-dev" / "active_project"
    # Act
    path = active_project_file()
    # Assert
    assert path == expected
