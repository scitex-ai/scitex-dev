"""Invalid kind containers produce registry validation errors, not hash errors."""

from pathlib import Path

import pytest

from scitex_dev.hosts import HOST_KINDS, HostRecord, HostRegistryError, list_hosts


@pytest.mark.parametrize(
    "kind", [["storage"], {"kind": "storage"}, {"storage"}, [], {}, set(), 0, True, None, "invalid"]
)
def test_direct_record_rejects_invalid_kind_with_registry_error(kind) -> None:
    # Arrange
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="invalid kind"):
        HostRecord("owned-host", kind, None, "/owned/state")


@pytest.mark.parametrize("kind", sorted(HOST_KINDS))
def test_direct_record_keeps_each_valid_kind(kind: str) -> None:
    # Arrange
    # Act
    record = HostRecord("owned-host", kind, None, "/owned/state")
    # Assert
    assert (record.name, record.kind, record.scitex_root) == ("owned-host", kind, "/owned/state")


@pytest.mark.parametrize("value", ["[storage]", "{kind: storage}", "[]", "{}", "42", "true"])
def test_yaml_kind_shapes_raise_registry_error(tmp_path: Path, value: str) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text(f'hosts:\n  owned-host:\n    kind: {value}\n    scitex_root: "/owned/state"\n')
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        list_hosts(hosts_path=path)
