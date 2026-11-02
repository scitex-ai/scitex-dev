"""Real directory/metadata controls for isolated-child test runtime paths."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.scitex_dev._child_runtime import (
    ChildRuntimeError,
    _trusted_target_site,
    child_runtime_paths,
)


@pytest.fixture
def context(tmp_path):
    root = tmp_path / "job"
    root.mkdir(mode=0o700)
    for name in ("site", "scitex", "runtime", "cache"):
        (root / name).mkdir(mode=0o700)
    environment = {
        "SCITEX_DIR": str(root / "scitex"),
        "XDG_RUNTIME_DIR": str(root / "runtime"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(tmp_path / "untrusted"),
    }
    return root, environment


def test_owned_target_does_not_inherit_other_parent_paths(context):
    """Only the exact attested site can supplement a child, not other entries."""
    # Arrange
    root, environment = context
    paths = ["/untrusted/arbitrary", str(root / "site")]
    # Act
    selected = _trusted_target_site(root, environment=environment, parent_paths=paths)
    # Assert
    assert selected == root / "site"


def test_user_site_must_be_disabled(context):
    """A declared target does not authorize the user's ambient site."""
    # Arrange
    root, original = context
    environment = dict(original, PYTHONNOUSERSITE="0")
    # Act
    # Assert
    with pytest.raises(ChildRuntimeError):
        _trusted_target_site(
            root, environment=environment, parent_paths=[str(root / "site")]
        )


def test_fixture_state_paths_do_not_change_import_path_authority(context):
    """Independent store shields and XDG fixtures cannot add or remove sites."""
    # Arrange
    root, original = context
    environment = dict(
        original,
        SCITEX_DIR="/fixture/shield",
        XDG_RUNTIME_DIR="/fixture/runtime",
        XDG_CACHE_HOME="/fixture/cache",
    )
    # Act
    selected = _trusted_target_site(
        root, environment=environment, parent_paths=[str(root / "site")]
    )
    # Assert
    assert selected == root / "site"


def test_target_not_on_actual_parent_path_is_rejected(context):
    """An environment hint cannot introduce a site the parent did not select."""
    # Arrange
    root, environment = context
    # Act
    # Assert
    with pytest.raises(ChildRuntimeError):
        _trusted_target_site(
            root, environment=environment, parent_paths=["/foreign/site"]
        )


def test_world_writable_target_is_rejected(context):
    """The owned target still must not be modifiable by other users."""
    # Arrange
    root, environment = context
    (root / "site").chmod(0o777)
    # Act
    # Assert
    with pytest.raises(ChildRuntimeError):
        _trusted_target_site(
            root, environment=environment, parent_paths=[str(root / "site")]
        )


def test_linked_target_is_rejected(context, tmp_path):
    """A target symlink cannot point an isolated child at another environment."""
    # Arrange
    root, environment = context
    (root / "site").rmdir()
    foreign = tmp_path / "foreign"
    foreign.mkdir(mode=0o700)
    (root / "site").symlink_to(foreign, target_is_directory=True)
    # Act
    # Assert
    with pytest.raises(ChildRuntimeError):
        _trusted_target_site(root, environment=environment, parent_paths=[str(foreign)])


@contextmanager
def _foreign_metadata(root):
    metadata = root / "fixture_child_foreign-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: fixture-child-foreign\nVersion: 1.0\n"
    )
    sys.path.insert(0, str(root))
    try:
        yield
    finally:
        sys.path.remove(str(root))


def test_real_foreign_distribution_metadata_cannot_supply_a_child_site(tmp_path):
    """A discoverable foreign distribution is refused, never imported or copied."""
    # Arrange
    source = Path(__file__).resolve().parents[2] / "src"
    # Act
    # Assert
    with (
        _foreign_metadata(tmp_path),
        pytest.raises(ChildRuntimeError, match="outside the owned runtime"),
    ):
        child_runtime_paths(source, required_distributions=("fixture-child-foreign",))


def test_real_declared_runtime_paths_are_bounded_to_source_and_selected_site():
    """The actual resolved test dependencies can use the supported child helper."""
    # Arrange
    source = Path(__file__).resolve().parents[2] / "src"
    # Act
    paths = child_runtime_paths(
        source, required_distributions=("scitex-dev", "scitex-sdk", "Django")
    )
    # Assert
    assert paths[0] == str(source) and len(paths) in {1, 2}
