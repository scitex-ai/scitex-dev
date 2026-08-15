"""Unit tests for scitex_dev.hosts._connectivity and its parse path.

Covers: backward compatibility (a pre-connectivity hosts.yaml still parses),
reserved-vs-observed staying two facts, MAC/fingerprint normalisation, the
`net` block's closed key set, the naming rule's structural enforcement, and
the private-key-material refusal.

No mocks (NM001-003) — real temp hosts.yaml files throughout. One assert per
test (02_package/13_test-quality.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev.hosts import (
    HostConnectivity,
    HostRegistryError,
    NetRoute,
    net_name,
    resolve,
)

_LEGACY_YAML = """\
hosts:
  spartan:
    kind: hpc-login
    ssh_alias: spartan
    scitex_root: "/data/gpfs/x/.scitex"
"""

_FULL_YAML = """\
hosts:
  scitex-nas-03:
    kind: storage
    ssh_alias: scitex-nas-03
    scitex_root: "~/.scitex"
    lan: 192.168.11.133
    mac: 6C:1F:F7:40:50:11
    reported_hostname: DXP480TPLUS-994
    host_key_fingerprint: "256 SHA256:AbCd0123+/= root@nas (ED25519)"
    identity_file: ~/.ssh/id_mesh
    ssh_user: ywatanabe
    last_seen: 2026-08-13
    net:
      transport: cloudflared
      hostname: bastion.scitex.ai
"""

_UNRENEWED_LEASE_YAML = """\
hosts:
  scitex-compute-01:
    kind: compute
    ssh_alias: scitex-compute-01
    scitex_root: "~/.scitex"
    lan: 192.168.11.94
    reserved: 192.168.11.171
"""


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "hosts.yaml"
    p.write_text(content)
    return p


# -------- backward compatibility -------------------------------------------


def test_registry_without_connectivity_still_parses(tmp_path):
    # Arrange — every hosts.yaml in the fleet predates these fields.
    p = _write(tmp_path, _LEGACY_YAML)
    # Act
    record = resolve("spartan", hosts_path=p)
    # Assert
    assert record.connectivity.is_empty()


def test_registry_without_connectivity_keeps_its_old_fields(tmp_path):
    # Arrange
    p = _write(tmp_path, _LEGACY_YAML)
    # Act
    record = resolve("spartan", hosts_path=p)
    # Assert
    assert record.scitex_root == "/data/gpfs/x/.scitex"


def test_a_populated_record_is_not_empty(tmp_path):
    # Arrange
    p = _write(tmp_path, _FULL_YAML)
    # Act
    record = resolve("scitex-nas-03", hosts_path=p)
    # Assert
    assert not record.connectivity.is_empty()


# -------- reserved is not observed ------------------------------------------


def test_observed_address_is_read_into_lan(tmp_path):
    # Arrange — measured 2026-08-13: reserved .171, answering at .94.
    p = _write(tmp_path, _UNRENEWED_LEASE_YAML)
    # Act
    record = resolve("scitex-compute-01", hosts_path=p)
    # Assert
    assert record.connectivity.lan == "192.168.11.94"


def test_reserved_address_is_kept_separately(tmp_path):
    # Arrange
    p = _write(tmp_path, _UNRENEWED_LEASE_YAML)
    # Act
    record = resolve("scitex-compute-01", hosts_path=p)
    # Assert
    assert record.connectivity.reserved == "192.168.11.171"


def test_unrenewed_lease_is_reported_as_a_mismatch(tmp_path):
    # Arrange
    p = _write(tmp_path, _UNRENEWED_LEASE_YAML)
    # Act
    record = resolve("scitex-compute-01", hosts_path=p)
    # Assert
    assert record.connectivity.reservation_matches_observed is False


def test_missing_reservation_is_unknown_not_agreement():
    """`None`, never `True`. Not recording a reservation is not evidence."""
    # Arrange
    conn = HostConnectivity(lan="192.168.11.94")
    # Act
    verdict = conn.reservation_matches_observed
    # Assert
    assert verdict is None


# -------- normalisation ------------------------------------------------------


def test_mac_is_normalised_to_lowercase(tmp_path):
    # Arrange — the operator's notes carry both cases for the same fleet.
    p = _write(tmp_path, _FULL_YAML)
    # Act
    record = resolve("scitex-nas-03", hosts_path=p)
    # Assert
    assert record.connectivity.mac == "6c:1f:f7:40:50:11"


def test_a_malformed_mac_raises(tmp_path):
    # Arrange
    yaml_text = (
        "hosts:\n  x:\n    kind: compute\n    ssh_alias: x\n"
        '    scitex_root: "~/.scitex"\n    mac: not-a-mac\n'
    )
    p = _write(tmp_path, yaml_text)
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("x", hosts_path=p)


def test_fingerprint_is_extracted_from_a_full_ssh_keygen_line(tmp_path):
    """So the recorded value and the scanned value compare directly."""
    # Arrange
    p = _write(tmp_path, _FULL_YAML)
    # Act
    record = resolve("scitex-nas-03", hosts_path=p)
    # Assert
    assert record.connectivity.host_key_fingerprint == "SHA256:AbCd0123+/="


# -------- the naming rule ----------------------------------------------------


def test_net_alias_is_the_bare_name_plus_suffix(tmp_path):
    # Arrange
    p = _write(tmp_path, _FULL_YAML)
    # Act
    record = resolve("scitex-nas-03", hosts_path=p)
    # Assert
    assert record.net_alias == "scitex-nas-03-net"


def test_a_lan_only_host_has_no_net_alias(tmp_path):
    """None, not a fabricated name that would resolve and connect to nothing."""
    # Arrange
    p = _write(tmp_path, _UNRENEWED_LEASE_YAML)
    # Act
    record = resolve("scitex-compute-01", hosts_path=p)
    # Assert
    assert record.net_alias is None


def test_net_name_is_idempotent():
    # Arrange
    already = "scitex-nas-03-net"
    # Act
    twice = net_name(net_name(already))
    # Assert
    assert twice == "scitex-nas-03-net"


def test_a_bastion_route_has_no_lan_side_field_to_live_in():
    """The naming rule enforced STRUCTURALLY: `jump` exists only on NetRoute.

    This is the negative half of the operator's 2026-08-13 ruling. A bare
    name cannot acquire a bastion because there is nowhere on the LAN side to
    write one — asserted here so that adding such a field later trips a test
    rather than passing review as a convenience.
    """
    # Arrange
    lan_side_fields = set(HostConnectivity.__dataclass_fields__)
    # Act
    routing_fields = lan_side_fields & {"jump", "proxy_command", "bastion", "proxyjump"}
    # Assert
    assert routing_fields == set()


def test_an_unknown_net_transport_is_rejected():
    # Arrange
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        NetRoute(transport="carrier-pigeon")


def test_reverse_ssh_without_a_jump_is_rejected():
    """A stanza with nothing to hop through is a name that cannot connect."""
    # Arrange
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        NetRoute(transport="reverse-ssh")


def test_an_unknown_key_inside_net_is_rejected(tmp_path):
    """`proxycommand` for `proxy_command` would render a proxy-less stanza."""
    # Arrange
    yaml_text = (
        "hosts:\n  x:\n    kind: compute\n    ssh_alias: x\n"
        '    scitex_root: "~/.scitex"\n    net:\n'
        "      transport: cloudflared\n      proxycommand: oops\n"
    )
    p = _write(tmp_path, yaml_text)
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("x", hosts_path=p)


# -------- no private key material -------------------------------------------


def test_a_secret_shaped_field_name_is_refused(tmp_path):
    # Arrange — this file is read by every host in the fleet.
    yaml_text = (
        "hosts:\n  x:\n    kind: compute\n    ssh_alias: x\n"
        '    scitex_root: "~/.scitex"\n    private_key: whatever\n'
    )
    p = _write(tmp_path, yaml_text)
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("x", hosts_path=p)


def test_a_pem_header_in_any_value_is_refused(tmp_path):
    """Caught by CONTENT, not by field name — someone pastes it anywhere."""
    # Arrange
    yaml_text = (
        "hosts:\n  x:\n    kind: compute\n    ssh_alias: x\n"
        '    scitex_root: "~/.scitex"\n'
        '    reported_hostname: "-----BEGIN OPENSSH PRIVATE KEY-----"\n'
    )
    p = _write(tmp_path, yaml_text)
    # Act
    # Assert
    with pytest.raises(HostRegistryError):
        resolve("x", hosts_path=p)


def test_an_identity_file_PATH_is_allowed(tmp_path):
    """A path is not key material, and the whole point is to record which key."""
    # Arrange
    p = _write(tmp_path, _FULL_YAML)
    # Act
    record = resolve("scitex-nas-03", hosts_path=p)
    # Assert
    assert record.connectivity.identity_file == "~/.ssh/id_mesh"


# -------- serialization ------------------------------------------------------


def test_to_dict_always_carries_a_connectivity_key(tmp_path):
    """Present-and-null, so a consumer never has to date the producer."""
    # Arrange
    p = _write(tmp_path, _LEGACY_YAML)
    # Act
    payload = resolve("spartan", hosts_path=p).to_dict()
    # Assert
    assert payload["connectivity"]["lan"] is None


def test_to_dict_serializes_the_net_route(tmp_path):
    # Arrange
    p = _write(tmp_path, _FULL_YAML)
    # Act
    payload = resolve("scitex-nas-03", hosts_path=p).to_dict()
    # Assert
    assert payload["connectivity"]["net"]["hostname"] == "bastion.scitex.ai"


# EOF
