"""DHCP declarations must distinguish invalid registries from empty scope."""

from pathlib import Path

import pytest

from scitex_dev.hosts import HostRegistryError, packaged_default_requested_addresses
from scitex_dev.hosts._dhcp import provide_request_address_specs


@pytest.mark.parametrize(
    "text", ["[]", "false", "hosts: []", "hosts: [unterminated",
             "hosts:\n  broken: []", "hosts:\n  broken:\n    kind: invalid"],
)
def test_provider_propagates_invalid_registry(tmp_path: Path, text: str) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text(text + "\n")
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        provide_request_address_specs(hosts_path=path)


def test_provider_propagates_unexpected_decoding_failure(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_bytes(b"\xff")
    # Act
    # Assert
    with pytest.raises(UnicodeDecodeError):
        provide_request_address_specs(hosts_path=path)


@pytest.mark.parametrize("text", ["", "null", "{}", "hosts: null", "hosts: {}"])
def test_provider_keeps_valid_empty_registry(tmp_path: Path, text: str) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text(text + "\n")
    # Act
    specs = provide_request_address_specs(hosts_path=path)
    # Assert
    assert specs == []


@pytest.mark.parametrize("kind", ["storage", "workstation", "hpc-login"])
def test_provider_keeps_noncompute_host_out_of_scope(tmp_path: Path, kind: str) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text(f"hosts:\n  scitex-compute-01:\n    kind: {kind}\n    scitex_root: /owned/state\n")
    # Act
    specs = provide_request_address_specs(hosts_path=path)
    # Assert
    assert specs == []


def test_provider_keeps_compute_host_packaged_request(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text("hosts:\n  scitex-compute-01:\n    kind: compute\n    scitex_root: /owned/state\n")
    expected = packaged_default_requested_addresses()["scitex-compute-01"]
    # Act
    specs = provide_request_address_specs(hosts_path=path)
    # Assert
    assert [(s.hosts, s.content, s.apply_command) for s in specs] == [
        (("scitex-compute-01",), f"[DHCPv4]\nRequestAddress={expected}\n", "networkctl reload")
    ]
