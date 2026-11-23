"""First-use registry seeding preserves existing entries and link targets."""

import os
from pathlib import Path

import pytest

from scitex_dev.hosts import create_default_hosts_yaml
from scitex_dev.hosts._seed import _DEFAULT_HOSTS_YAML


@pytest.fixture(params=["absolute", "relative", "missing-parent", "chain"])
def dangling_registry(tmp_path: Path, request):
    kind = request.param
    path = tmp_path / "registry" / "hosts.yaml"
    path.parent.mkdir()
    target = tmp_path / "target" / "hosts.yaml"
    if kind != "missing-parent":
        target.parent.mkdir()
    link_target = str(target)
    if kind == "relative":
        link_target = os.path.relpath(target, path.parent)
    elif kind == "chain":
        intermediate = tmp_path / "chain.yaml"
        intermediate.symlink_to(target)
        link_target = str(intermediate)
    path.symlink_to(link_target)
    before = path.lstat()
    return path, target, link_target, before


def test_seed_leaves_dangling_link_and_target_untouched(dangling_registry) -> None:
    # Arrange
    path, target, link_target, before = dangling_registry
    # Act
    result = create_default_hosts_yaml(path)
    # Assert
    assert (result, target.exists(), path.is_symlink(), os.readlink(path), path.lstat().st_ino) == (
        path, False, True, link_target, before.st_ino
    )

@pytest.mark.parametrize("body", ["", "owned existing data\n", _DEFAULT_HOSTS_YAML])
def test_seed_keeps_existing_regular_file(tmp_path: Path, body: str) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text(body)
    before = path.stat()
    # Act
    result = create_default_hosts_yaml(path)
    # Assert
    assert (result, path.read_text(), path.stat().st_ino, path.stat().st_mtime_ns) == (
        path, body, before.st_ino, before.st_mtime_ns
    )


@pytest.mark.parametrize("as_string", [False, True])
def test_seed_creates_missing_file_with_packaged_bytes(tmp_path: Path, as_string: bool) -> None:
    # Arrange
    path = tmp_path / "nested" / "hosts.yaml"
    argument = str(path) if as_string else path
    # Act
    result = create_default_hosts_yaml(argument)
    # Assert
    assert (result, path.read_text()) == (path, _DEFAULT_HOSTS_YAML)


def test_seed_keeps_existing_valid_link(tmp_path: Path) -> None:
    # Arrange
    target = tmp_path / "target.yaml"
    target.write_text("owned existing data\n")
    path = tmp_path / "hosts.yaml"
    path.symlink_to(target)
    before = target.stat()
    # Act
    result = create_default_hosts_yaml(path)
    # Assert
    assert (result, path.is_symlink(), target.read_text(), target.stat().st_mtime_ns) == (
        path, True, "owned existing data\n", before.st_mtime_ns
    )


def test_seed_keeps_existing_directory(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.mkdir()
    before = path.stat()
    # Act
    result = create_default_hosts_yaml(path)
    # Assert
    assert (result, path.is_dir(), path.stat().st_ino) == (path, True, before.st_ino)
