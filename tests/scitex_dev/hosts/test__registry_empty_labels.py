"""Empty runner labels do not identify a declared runner destination."""

from pathlib import Path

import pytest

from scitex_dev.hosts import HostRegistryError, find_runner_host


@pytest.fixture
def empty_registry(tmp_path: Path) -> Path:
    path = tmp_path / "hosts.yaml"
    path.write_text("hosts: {}\n")
    return path


@pytest.fixture
def local_registry(tmp_path: Path) -> Path:
    path = tmp_path / "local.yaml"
    path.write_text("hosts:\n  owned-runner:\n    kind: compute\n    scitex_root: /owned/state\n    runner_labels: [[self-hosted, Linux, X64, owned-ci]]\n")
    return path


@pytest.mark.parametrize("labels", [[], (), set(), frozenset(), iter(()), (x for x in ())])
@pytest.mark.parametrize("include_floor", [True, False])
def test_empty_labels_never_match_floor(empty_registry: Path, labels, include_floor: bool) -> None:
    # Arrange
    # Act
    result = find_runner_host(labels, hosts_path=empty_registry, include_packaged_floor=include_floor)
    # Assert
    assert result is None


def test_empty_labels_do_not_match_when_local_runner_exists(local_registry: Path) -> None:
    # Arrange
    # Act
    result = find_runner_host([], hosts_path=local_registry)
    # Assert
    assert result is None


@pytest.mark.parametrize("include_floor", [True, False])
def test_nonempty_local_match_is_preserved(local_registry: Path, include_floor: bool) -> None:
    # Arrange
    # Act
    result = find_runner_host(["self-hosted", "owned-ci"], hosts_path=local_registry, include_packaged_floor=include_floor)
    # Assert
    assert result.name == "owned-runner"


@pytest.mark.parametrize("include_floor", [True, False])
def test_nonempty_unserved_request_stays_none(empty_registry: Path, include_floor: bool) -> None:
    # Arrange
    # Act
    result = find_runner_host(["owned-never-declared"], hosts_path=empty_registry, include_packaged_floor=include_floor)
    # Assert
    assert result is None


def test_empty_request_keeps_selected_registry_validation(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "invalid.yaml"
    path.write_text("hosts: []\n")
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        find_runner_host([], hosts_path=path)
