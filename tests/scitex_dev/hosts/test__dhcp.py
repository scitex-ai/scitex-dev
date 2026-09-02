#!/usr/bin/env python3
"""Tests for the fleet network floor (``scitex_dev.hosts._dhcp``).

The design these replace emitted ONE DROP-IN PER HOST, keyed on that host's
interface NAME. It was wrong for two of four machines on 2026-09-02
(compute-01 and compute-02 both mapped to ``enp8s0``, which exists on no
host), and the module's own docstring had predicted why: a renamed
interface leaves the drop-in byte-correct on disk and applying to nothing.

So the tests below assert the OPPOSITE properties. The old file asserted
"one spec per host", "each spec targets exactly one host", "the declared
address comes from the registry" — every one of those is now a defect.

NO MOCKS. Registry-dependent tests write a real ``hosts.yaml`` into
``tmp_path`` and pass it in, because the behaviour under test is precisely
what the module does with a REAL registry that says something particular.
One assert per test (STX-TQ007).
"""

from __future__ import annotations

import pytest
import yaml

import hashlib

from scitex_dev.hosts._dhcp import (
    _FLEET_NETPLAN_CONTENT,
    _FLEET_NETPLAN_PATH,
    _FLEET_NETPLAN_SHA256,
    provide_dhcp_specs,
)
from scitex_dev.hosts._registry import HostRegistryError


def _write_registry(tmp_path, hosts: dict) -> str:
    path = tmp_path / "hosts.yaml"
    path.write_text(yaml.safe_dump({"hosts": hosts}), encoding="utf-8")
    return str(path)


@pytest.fixture
def registry_with_compute(tmp_path) -> str:
    """A registry shaped like the real fleet: compute plus other kinds."""
    return _write_registry(
        tmp_path,
        {
            "scitex-compute-01": {"kind": "compute", "scitex_root": "~/.scitex"},
            "scitex-compute-02": {"kind": "compute", "scitex_root": "~/.scitex"},
            "scitex-nas-01": {"kind": "storage", "scitex_root": "~/.scitex"},
            "scitex-laptop-01": {"kind": "workstation", "scitex_root": "~/.scitex"},
            "spartan": {"kind": "hpc-login", "scitex_root": "~/.scitex"},
        },
    )


@pytest.fixture
def registry_without_compute(tmp_path) -> str:
    """The state MEASURED inside an agent container on 2026-09-02.

    The container resolves ``~/.scitex/dev/hosts.yaml`` under /home/agent,
    which is not the host registry: 6 records, zero compute, and still
    naming the retired `mba` / `ywata-note-win`.
    """
    return _write_registry(
        tmp_path,
        {
            "scitex-nas-01": {"kind": "storage", "scitex_root": "~/.scitex"},
            "spartan": {"kind": "hpc-login", "scitex_root": "~/.scitex"},
        },
    )


class TestTheFloorHasNoPerHostContent:
    """The property that makes this design survive an interface rename."""

    def test_exactly_one_spec_is_emitted(self, registry_with_compute):
        # Arrange
        path = registry_with_compute

        # Act
        specs = provide_dhcp_specs(hosts_path=path)

        # Assert — one file for the whole fleet. The old design emitted one
        # per host, which is what allowed two of them to be wrong.
        assert len(specs) == 1

    def test_the_content_names_no_interface(self, registry_with_compute):
        # Arrange
        path = registry_with_compute

        # Act
        content = provide_dhcp_specs(hosts_path=path)[0].content

        # Assert — the whole failure mode was a literal interface name in a
        # config file. `enp` appearing anywhere here would reintroduce it.
        assert "enp" not in content

    def test_the_content_matches_ethernet_ports_by_glob(
        self, registry_with_compute
    ):
        # Arrange
        path = registry_with_compute

        # Act
        parsed = yaml.safe_load(provide_dhcp_specs(hosts_path=path)[0].content)

        # Assert
        assert parsed["network"]["ethernets"]["fleet-en"]["match"] == {
            "name": "en*"
        }

    def test_a_missing_port_does_not_hold_up_boot(self, registry_with_compute):
        # Arrange
        path = registry_with_compute

        # Act
        parsed = yaml.safe_load(provide_dhcp_specs(hosts_path=path)[0].content)

        # Assert — without `optional`, a machine with an unplugged port
        # waits for it at boot, which is its own way to be unreachable.
        assert parsed["network"]["ethernets"]["fleet-en"]["optional"] is True

    def test_no_address_is_pinned_in_the_file(self, registry_with_compute):
        # Arrange
        path = registry_with_compute

        # Act
        parsed = yaml.safe_load(provide_dhcp_specs(hosts_path=path)[0].content)

        # Assert — the pin lives in the router's MAC reservation. Pinning
        # here would require naming a port, which is the fragility removed.
        assert "addresses" not in parsed["network"]["ethernets"]["fleet-en"]


class TestTheFloorIsWrittenWhereTheHandAppliedOneLives:
    """Same path means an idempotent overwrite, not a second floor."""

    def test_the_path_is_the_canonical_netplan_file(
        self, registry_with_compute
    ):
        # Arrange
        path = registry_with_compute

        # Act
        spec_path = provide_dhcp_specs(hosts_path=path)[0].path

        # Assert — a DIFFERENT filename would leave two floors on disk and
        # let sort order decide, which is the trap this design removes.
        assert spec_path == "/etc/netplan/99-scitex-fleet.yaml"

    def test_the_module_constant_and_the_spec_agree(
        self, registry_with_compute
    ):
        # Arrange
        path = registry_with_compute

        # Act
        spec = provide_dhcp_specs(hosts_path=path)[0]

        # Assert
        assert (spec.path, spec.content) == (
            _FLEET_NETPLAN_PATH,
            _FLEET_NETPLAN_CONTENT,
        )


class TestScopingBranchesOnKind:
    """Netplan runs on the compute machines and nowhere else in the fleet."""

    def test_only_compute_hosts_are_targeted(self, registry_with_compute):
        # Arrange
        path = registry_with_compute

        # Act
        hosts = provide_dhcp_specs(hosts_path=path)[0].hosts

        # Assert — NAS appliances, laptops and Spartan do not run netplan.
        assert hosts == ("scitex-compute-01", "scitex-compute-02")

    def test_a_registry_with_no_compute_host_refuses(
        self, registry_without_compute
    ):
        # Arrange
        path = registry_without_compute

        # Act
        def generate():
            return provide_dhcp_specs(hosts_path=path)

        # Assert — REFUSING is the point. An empty `hosts` tuple means EVERY
        # host to HostConfigSpec.applies_to, so returning () here would widen
        # this spec to the whole fleet rather than narrowing it to none,
        # writing a netplan file onto appliances that have no netplan.
        with pytest.raises(HostRegistryError, match="no `kind: compute` host"):
            generate()

    def test_the_refusal_names_the_registry_it_read(
        self, registry_without_compute
    ):
        # Arrange
        path = registry_without_compute

        # Act
        try:
            provide_dhcp_specs(hosts_path=path)
            message = ""
        except HostRegistryError as exc:
            message = str(exc)

        # Assert — the failure is a WRONG VANTAGE POINT, so the message is
        # useless unless it says which file it actually read. Matching the
        # distinctive phrase too: an earlier version of this test passed
        # because a MALFORMED fixture made the PARSER raise the same
        # exception type, which is a pass for the wrong reason.
        assert "no `kind: compute` host" in message and path in message


class TestTheGeneratedBytesAreTheDeployedBytes:
    """Byte-identity with the file sac hand-applied, as a test not a hope.

    I could not read the deployed file to compare — it is mode 0600 root and
    this agent is not root. Identity was established two other ways: its size
    (466 bytes, from `ls -la` on compute-04) and its sha256, measured by sac
    on the live file. Pinning the digest here means a change to the content
    has to change this constant deliberately, and the first `host-config
    apply` after this lands stays a no-op.
    """

    def test_the_content_hashes_to_the_deployed_digest(self):
        # Arrange
        content = _FLEET_NETPLAN_CONTENT

        # Act
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Assert
        assert digest == _FLEET_NETPLAN_SHA256

    def test_the_content_is_the_size_measured_on_the_host(self):
        # Arrange
        content = _FLEET_NETPLAN_CONTENT

        # Act
        size = len(content.encode("utf-8"))

        # Assert — `ls -la /etc/netplan/` on compute-04 reported 466 bytes.
        # An independent witness to the digest above: two different
        # properties of the same file, measured separately.
        assert size == 466
