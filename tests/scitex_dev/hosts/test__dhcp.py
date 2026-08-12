"""The DHCP requested-address drop-ins — declared, checkable, and honest.

Three properties are worth pinning, and they are not the obvious ones.

FIRST, the declaration must not claim a compliance it cannot deliver. Five
of the nine fleet hosts have no supported requested-address knob (WSL2
where Windows owns the lease, macOS, two QNAPs whose `/etc` is a ramdisk,
and a UGREEN NAS whose vendor script rewrites dhclient.conf at boot). For
those, emitting a spec would produce a file that is present, correct, and
read by nothing — with every subsequent `check` reporting `ok` forever.
Silence is the correct output, so silence is tested.

SECOND, the address must come from the registry rather than be repeated
here. Two copies of an address map is how a host ends up on an address
nobody declared.

THIRD, `-01` and `-02` genuinely share an interface name, so their specs
share a PATH while applying to different machines. That is not a
collision, and `discover_host_config` must not drop one of them — the
failure mode is one address silently applied to two hosts.

No mocks (NM001-003): the real provider, the real aggregator, the real
`evaluate` against a tmp_path root. One assert per test (STX-TQ007),
Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

from scitex_dev.hosts._dhcp import provide_dhcp_specs
from scitex_dev.host_config import (
    STATE_NOT_APPLICABLE,
    STATE_OK,
    directives_of,
    discover_host_config,
    evaluate,
)
from scitex_dev.hosts._seed import FLEET_REQUESTED_ADDRESSES

_NETWORKD_FLEET = [
    "scitex-compute-01",
    "scitex-compute-02",
    "scitex-compute-03",
    "scitex-compute-04",
]

#: The five machines the fleet map names but this module must NOT declare.
#: Measured 2026-08-12 — see the module docstring in hosts/_dhcp.py.
_NO_MECHANISM = [
    "ywata-note-win",
    "mba",
    "scitex-nas-01",
    "scitex-nas-02",
    "scitex-nas-03",
]


def _by_host(specs):
    return {spec.hosts[0]: spec for spec in specs if spec.hosts}


def test_one_spec_per_configurable_host():
    # Arrange
    expected = len(_NETWORKD_FLEET)
    # Act
    specs = provide_dhcp_specs()
    # Assert
    assert len(specs) == expected


def test_every_configurable_host_is_declared():
    # Arrange
    expected = set(_NETWORKD_FLEET)
    # Act
    found = set(_by_host(provide_dhcp_specs()))
    # Assert
    assert found == expected


def test_hosts_without_a_mechanism_get_no_spec():
    # Arrange — the whole point: a file read by nothing would report `ok`
    # forever and hide that these machines are not actually pinned.
    declared = set(_by_host(provide_dhcp_specs()))
    # Act
    overreach = declared.intersection(_NO_MECHANISM)
    # Assert
    assert not overreach


def test_each_spec_targets_exactly_one_host():
    # Arrange — an empty `hosts` tuple means EVERY host, which would put
    # one machine's address on all of them.
    specs = provide_dhcp_specs()
    # Act
    widths = {len(spec.hosts) for spec in specs}
    # Assert
    assert widths == {1}


def test_the_declared_address_comes_from_the_registry():
    # Arrange
    specs = _by_host(provide_dhcp_specs())
    # Act
    rendered = {
        host: directives_of(spec.content)["RequestAddress"]
        for host, spec in specs.items()
    }
    # Assert
    assert all(FLEET_REQUESTED_ADDRESSES[h] == a for h, a in rendered.items())


def test_the_request_address_directive_is_live_not_commented():
    # Arrange — `directives_of` ignores comments, so this proves the value
    # is a real directive and not part of the explanatory banner.
    spec = _by_host(provide_dhcp_specs())["scitex-compute-04"]
    # Act
    directives = directives_of(spec.content)
    # Assert
    assert directives["RequestAddress"] == "192.168.11.174"


def test_the_body_states_that_this_is_only_a_request():
    # Arrange — the honest limit belongs in the file itself: whoever reads
    # it is debugging why the machine is not on the expected address.
    spec = _by_host(provide_dhcp_specs())["scitex-compute-04"]
    # Act
    body = spec.content
    # Assert
    assert "REQUEST, NOT A RESERVATION" in body


def test_the_drop_in_sits_beside_the_netplan_unit():
    # Arrange — netplan rewrites /run on every apply, so the declaration
    # has to be a drop-in under /etc rather than an edit to its unit.
    spec = _by_host(provide_dhcp_specs())["scitex-compute-04"]
    # Act
    path = spec.path
    # Assert
    assert path == (
        "/etc/systemd/network/10-netplan-enp3s0f0.network.d/"
        "50-scitex-requested-address.conf"
    )


def test_every_spec_requires_networkctl():
    # Arrange — without networkd the file is inert, and `check` would
    # report ok on a host where the declaration does nothing.
    specs = provide_dhcp_specs()
    # Act
    preconditions = {spec.requires_command for spec in specs}
    # Assert
    assert preconditions == {"networkctl"}


def test_every_spec_observes_its_own_interface():
    # Arrange — the interface differs per host, so one shared command
    # would report the wrong NIC on three of the four.
    specs = _by_host(provide_dhcp_specs())
    # Act
    commands = {h: s.verify_command for h, s in specs.items()}
    # Assert
    assert commands["scitex-compute-03"] == "ip -4 -o addr show enp35s0f0"


def test_apply_reloads_rather_than_reconfigures():
    # Arrange — `networkctl reconfigure` re-runs DHCP and would move the
    # address (and cut the ssh session applying it) on the spot.
    specs = provide_dhcp_specs()
    # Act
    commands = {spec.apply_command for spec in specs}
    # Assert
    assert commands == {"networkctl reload"}


def test_two_hosts_sharing_an_interface_name_both_survive_discovery():
    # Arrange — -01 and -02 both run enp8s0, so their specs share a path.
    # Dropping one would silently apply a single address to two machines.
    provider = provide_dhcp_specs
    # Act
    found = discover_host_config(
        extra_providers=[provider], include_entry_points=False
    )
    # Assert
    assert len(found) == len(_NETWORKD_FLEET)


def test_a_spec_is_not_applicable_on_a_host_it_does_not_target(tmp_path):
    # Arrange — a compute-04 drop-in must never read as drift on -01.
    spec = _by_host(provide_dhcp_specs())["scitex-compute-04"]
    # Act
    status = evaluate(spec, root=str(tmp_path), hostname="scitex-compute-01")
    # Assert
    assert status.state == STATE_NOT_APPLICABLE


def test_a_converged_host_reports_ok(tmp_path):
    # Arrange — write the declared file exactly and check it reads back as
    # converged, so `ok` is reachable rather than theoretical.
    spec = _by_host(provide_dhcp_specs())["scitex-compute-04"]
    target = tmp_path / spec.path.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(spec.content)
    target.chmod(0o644)
    # Act
    status = evaluate(spec, root=str(tmp_path), hostname="scitex-compute-04")
    # Assert
    assert status.state == STATE_OK


def test_the_content_ends_with_a_newline():
    # Arrange — HostConfigSpec rejects a body without one, so this pins the
    # renderer rather than the validator.
    specs = provide_dhcp_specs()
    # Act
    endings = {spec.content.endswith("\n") for spec in specs}
    # Assert
    assert endings == {True}


def test_spec_names_are_unique():
    # Arrange — `name` is the de-duplication key; a collision would drop a
    # host from the declaration with only a logged warning.
    specs = provide_dhcp_specs()
    # Act
    names = [spec.name for spec in specs]
    # Assert
    assert len(set(names)) == len(names)


# EOF
