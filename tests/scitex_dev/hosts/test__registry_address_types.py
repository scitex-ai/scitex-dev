"""Direct records require IPv4 strings, matching the YAML field contract."""

import ipaddress
from pathlib import Path

import pytest

from scitex_dev.hosts import HostRecord, HostRegistryError, list_hosts


@pytest.mark.parametrize(
    "address",
    [0, 1, 3232238535, True, False, b"\xc0\xa8\x0b\xc7",
     ipaddress.IPv4Address("192.168.11.199"), 1.5, [], {}, set(),
     bytearray(b"\xc0\xa8\x0b\xc7"), -1, 2**32],
)
def test_direct_address_rejects_non_string_values(address) -> None:
    # Arrange
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="requested_address.*IPv4"):
        HostRecord("owned-host", "compute", None, "/owned/state", requested_address=address)


@pytest.mark.parametrize("address", [None, "0.0.0.0", "127.0.0.1", "192.168.11.199", "255.255.255.255"])
def test_direct_address_keeps_literal_or_no_preference(address) -> None:
    # Arrange
    # Act
    record = HostRecord("owned-host", "compute", None, "/owned/state", requested_address=address)
    # Assert
    assert record.to_dict()["requested_address"] == address


@pytest.mark.parametrize("address", ["", " ", "192.168", "192.168.11.999", "::1", "192.168.11.199/24"])
def test_direct_address_keeps_rejecting_malformed_strings(address: str) -> None:
    # Arrange
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="requested_address.*IPv4"):
        HostRecord("owned-host", "compute", None, "/owned/state", requested_address=address)


@pytest.mark.parametrize("value", ["0", "true", "[192.168.11.199]", "{}", "192.168", "!!binary wKgLxw=="])
def test_yaml_address_keeps_rejecting_non_strings(tmp_path: Path, value: str) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text(f'hosts:\n  owned-host:\n    kind: compute\n    scitex_root: /owned/state\n    requested_address: {value}\n')
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="requested_address"):
        list_hosts(hosts_path=path)
