"""Registry YAML shape checks keep malformed values distinct from empty state."""

from pathlib import Path

import pytest

from scitex_dev.hosts import HostRegistryError, list_hosts

_INVALID = ['[]', '[entry]', 'false', '0', '""', '"entry"', '3.5']


@pytest.mark.parametrize("document", _INVALID)
def test_top_document_requires_mapping(tmp_path: Path, document: str) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text(document + "\n", encoding="utf-8")
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="mapping"):
        list_hosts(hosts_path=path)


@pytest.mark.parametrize("value", _INVALID)
def test_hosts_block_requires_mapping(tmp_path: Path, value: str) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text("hosts: " + value + "\n", encoding="utf-8")
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="mapping"):
        list_hosts(hosts_path=path)


@pytest.mark.parametrize(
    "document", ["", "null\n", "{}\n", "hosts: null\n", "hosts: {}\n", "metadata: inert\n"]
)
def test_existing_empty_registry_shapes_remain_valid(tmp_path: Path, document: str) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text(document, encoding="utf-8")
    # Act
    records = list_hosts(hosts_path=path)
    # Assert
    assert records == []


def test_valid_registry_mapping_still_resolves_records(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text(
        'hosts:\n  owned-host:\n    kind: storage\n    scitex_root: "/owned/state"\n',
        encoding="utf-8",
    )
    # Act
    records = list_hosts(hosts_path=path)
    # Assert
    assert [(record.name, record.kind, record.scitex_root) for record in records] == [
        ("owned-host", "storage", "/owned/state")
    ]
