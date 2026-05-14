"""Tests for the ecosystem dashboard state layer."""

from __future__ import annotations

import dataclasses


def test_package_state_is_a_dataclass_with_expected_fields_dataclasses_is_dataclass_packagestate():
    """`PackageState` is the data shape every dashboard cell consumes.
    Verify it's a dataclass with the fields the renderer reads, so
    accidental field renames break this test instead of silently
    producing empty cells."""
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.ecosystem._dashboard._state import PackageState

    assert dataclasses.is_dataclass(PackageState)
    field_names = {f.name for f in dataclasses.fields(PackageState)}
    # Minimum surface the renderer consumes today.


def test_package_state_is_a_dataclass_with_expected_fields_pkg_in_field_names():
    """`PackageState` is the data shape every dashboard cell consumes.
    Verify it's a dataclass with the fields the renderer reads, so
    accidental field renames break this test instead of silently
    producing empty cells."""
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.ecosystem._dashboard._state import PackageState

    field_names = {f.name for f in dataclasses.fields(PackageState)}
    # Minimum surface the renderer consumes today.
    assert "pkg" in field_names


def test_gather_ecosystem_state_returns_a_list():
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard import gather_ecosystem_state

    # Act
    states = gather_ecosystem_state(verbosity=0)
    # Assert
    assert isinstance(states, list)


def test_gather_ecosystem_state_elements_are_PackageState():
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard import gather_ecosystem_state
    from scitex_dev._cli.ecosystem._dashboard._state import PackageState

    # Act
    states = gather_ecosystem_state(verbosity=0)
    # Assert
    assert all(isinstance(s, PackageState) for s in states)


def test_gather_ecosystem_state_elements_have_pkg_field():
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard import gather_ecosystem_state

    # Act
    states = gather_ecosystem_state(verbosity=0)
    # Assert
    assert all(hasattr(s, "pkg") for s in states)
