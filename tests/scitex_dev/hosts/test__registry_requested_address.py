"""The fleet's DESIRED LAN address map — declared state, never observed.

`requested_address` is rendered verbatim into a file a DHCP client parses,
and a DHCP client does not complain about a malformed directive: it drops
it and keeps whatever lease it already had. That failure looks EXACTLY like
"the server ignored our request", which is a legitimate and expected
outcome of option 50 — so the two would be indistinguishable in the field.
Everything here exists to make the malformed case fail at parse/construct
time, where it is still telling.

The other half is the FLOOR. `create_default_hosts_yaml` only writes when
the file is missing, so every host that had a registry before this field
existed holds a copy with no addresses in it. `list_requested_addresses`
must not read that as "the fleet has no map".

No mocks (NM001-003): real YAML written to tmp_path, read through the real
parser. One assert per test (STX-TQ007), Arrange/Act/Assert (STX-TQ002).
"""

from __future__ import annotations

import pytest

from scitex_dev.hosts import (
    HostRecord,
    HostRegistryError,
    list_requested_addresses,
    packaged_default_requested_addresses,
    resolve,
)
from scitex_dev.hosts._seed import FLEET_REQUESTED_ADDRESSES

_ONE_HOST = """\
hosts:
  boxy:
    kind: compute
    ssh_alias: boxy
    scitex_root: "~/.scitex"
    requested_address: "192.168.11.199"
"""

_NO_ADDRESS = """\
hosts:
  boxy:
    kind: compute
    ssh_alias: boxy
    scitex_root: "~/.scitex"
"""

_UNQUOTED_SHORT_ADDRESS = """\
hosts:
  boxy:
    kind: compute
    ssh_alias: boxy
    scitex_root: "~/.scitex"
    requested_address: 192.168
"""

_EMPTY_ADDRESS = """\
hosts:
  boxy:
    kind: compute
    ssh_alias: boxy
    scitex_root: "~/.scitex"
    requested_address: "   "
"""

_NOT_AN_ADDRESS = """\
hosts:
  boxy:
    kind: compute
    ssh_alias: boxy
    scitex_root: "~/.scitex"
    requested_address: "192.168.11.999"
"""


def _write(tmp_path, text):
    path = tmp_path / "hosts.yaml"
    path.write_text(text)
    return path


def test_a_declared_address_survives_the_round_trip(tmp_path):
    # Arrange
    path = _write(tmp_path, _ONE_HOST)
    # Act
    record = resolve("boxy", hosts_path=path)
    # Assert
    assert record.requested_address == "192.168.11.199"


def test_a_host_with_no_preference_parses_to_none(tmp_path):
    # Arrange — omitting the field is the norm, not an error.
    path = _write(tmp_path, _NO_ADDRESS)
    # Act
    record = resolve("boxy", hosts_path=path)
    # Assert
    assert record.requested_address is None


def test_an_unquoted_short_address_is_rejected_rather_than_stringified(tmp_path):
    # Arrange — `192.168` is a FLOAT to YAML. str()-ing it would turn a
    # one-octet typo into a plausible-looking value nobody would question.
    path = _write(tmp_path, _UNQUOTED_SHORT_ADDRESS)
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="requested_address"):
        resolve("boxy", hosts_path=path)


def test_a_whitespace_only_address_is_rejected(tmp_path):
    # Arrange — indistinguishable from "no preference", which omitting the
    # field already says more clearly.
    path = _write(tmp_path, _EMPTY_ADDRESS)
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="empty"):
        resolve("boxy", hosts_path=path)


def test_an_out_of_range_octet_is_rejected_at_construction(tmp_path):
    # Arrange — .999 is the classic transposition of a real address; a DHCP
    # client would silently ignore the directive rather than report it.
    path = _write(tmp_path, _NOT_AN_ADDRESS)
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="IPv4"):
        resolve("boxy", hosts_path=path)


def test_a_bad_address_fails_the_dataclass_directly():
    # Arrange — the guard lives on HostRecord, so it holds for callers that
    # never go through YAML at all.
    # Act
    # Assert
    with pytest.raises(HostRegistryError, match="IPv4"):
        HostRecord(
            name="boxy",
            kind="compute",
            ssh_alias=None,
            scitex_root="~/.scitex",
            requested_address="not-an-address",
        )


def test_to_dict_carries_the_address():
    # Arrange — `host show --json` is how an operator reads the map.
    record = HostRecord(
        name="boxy",
        kind="compute",
        ssh_alias=None,
        scitex_root="~/.scitex",
        requested_address="192.168.11.199",
    )
    # Act
    payload = record.to_dict()
    # Assert
    assert payload["requested_address"] == "192.168.11.199"


def test_the_packaged_map_covers_all_nine_fleet_hosts():
    # Arrange — the operator approved exactly nine.
    # Act
    found = packaged_default_requested_addresses()
    # Assert
    assert len(found) == 9


def test_the_packaged_map_is_never_empty():
    # Arrange — an empty map is indistinguishable from "no host declares an
    # address", which would silently disable the whole scheme.
    # Act
    found = packaged_default_requested_addresses()
    # Assert
    assert found


def test_the_packaged_map_is_a_copy_a_caller_cannot_poison():
    # Arrange — one mutating caller must not rewrite the fleet declaration
    # for the rest of the process.
    packaged_default_requested_addresses()["scitex-compute-04"] = "10.0.0.1"
    # Act
    second = packaged_default_requested_addresses()
    # Assert
    assert second["scitex-compute-04"] == "192.168.11.174"


def test_every_packaged_address_is_a_valid_ipv4():
    # Arrange — the map is package data, so nothing else validates it.
    import ipaddress

    # Act
    parsed = [
        ipaddress.IPv4Address(value)
        for value in FLEET_REQUESTED_ADDRESSES.values()
    ]
    # Assert
    assert len(parsed) == len(FLEET_REQUESTED_ADDRESSES)


def test_no_two_hosts_are_declared_on_the_same_address():
    # Arrange — a duplicate would guarantee that at most one of the pair can
    # ever get what it asked for, with nothing reporting why.
    values = list(FLEET_REQUESTED_ADDRESSES.values())
    # Act
    unique = set(values)
    # Assert
    assert len(unique) == len(values)


def test_the_last_octet_encodes_the_role():
    # Arrange — 1NN workstation / 13N storage / 17N compute, the repair of
    # the operator's 10N/30N/70N scheme (30N and 70N exceed 255).
    prefixes = {
        host: address.rsplit(".", 1)[1][0]
        for host, address in FLEET_REQUESTED_ADDRESSES.items()
    }
    # Act
    compute = {v for k, v in prefixes.items() if k.startswith("scitex-compute")}
    # Assert
    assert compute == {"1"}


def test_storage_and_compute_occupy_distinct_bands():
    # Arrange — the identifying digit is the SECOND one: 13N vs 17N.
    bands = {
        host: address.rsplit(".", 1)[1][:2]
        for host, address in FLEET_REQUESTED_ADDRESSES.items()
    }
    nas = {v for k, v in bands.items() if k.startswith("scitex-nas")}
    compute = {v for k, v in bands.items() if k.startswith("scitex-compute")}
    # Act
    overlap = nas & compute
    # Assert
    assert not overlap


def test_every_declared_address_fits_in_an_octet():
    # Arrange — this is the exact defect that killed the original
    # 10N/30N/70N scheme, so it is worth a standing guard.
    octets = [
        int(address.rsplit(".", 1)[1])
        for address in FLEET_REQUESTED_ADDRESSES.values()
    ]
    # Act
    oversized = [o for o in octets if o > 255]
    # Assert
    assert not oversized


def test_the_seed_rows_agree_with_the_packaged_map(tmp_path):
    # Arrange — the seed YAML repeats two of the addresses for human
    # readers; a divergence there would make the registry contradict itself.
    import yaml

    from scitex_dev.hosts._seed import _DEFAULT_HOSTS_YAML

    rows = yaml.safe_load(_DEFAULT_HOSTS_YAML)["hosts"]
    # Act
    inline = {
        name: row["requested_address"]
        for name, row in rows.items()
        if row and row.get("requested_address")
    }
    # Assert
    assert all(FLEET_REQUESTED_ADDRESSES[k] == v for k, v in inline.items())


def test_a_registry_declaring_nothing_still_reports_the_fleet_map(tmp_path):
    # Arrange — the stale-file case: a hosts.yaml written before the field
    # existed. Reading it as "no map" is the silent disappearance this
    # floor exists to prevent.
    path = _write(tmp_path, _NO_ADDRESS)
    # Act
    found = list_requested_addresses(hosts_path=path)
    # Assert
    assert found["scitex-compute-04"] == "192.168.11.174"


def test_an_on_disk_declaration_overrides_the_packaged_map(tmp_path):
    # Arrange — an address must be correctable without cutting a release.
    path = _write(tmp_path, _ONE_HOST)
    # Act
    found = list_requested_addresses(hosts_path=path)
    # Assert
    assert found["boxy"] == "192.168.11.199"


def test_an_override_does_not_drop_the_other_hosts(tmp_path):
    # Arrange — a MERGE, not an either/or: one host declaring an address
    # must not hide the eight that did not.
    path = _write(tmp_path, _ONE_HOST)
    # Act
    found = list_requested_addresses(hosts_path=path)
    # Assert
    assert len(found) == 10


# EOF
