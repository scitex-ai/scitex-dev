#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/hosts/_dhcp.py
"""Make each fleet machine ASK for its declared LAN address (DHCP opt 50).

The address map itself is NOT here -- it lives in the host registry
(:data:`scitex_dev.hosts.FLEET_REQUESTED_ADDRESSES`), which is the single
source of truth for DESIRED state. This module only renders that desire
into the one file each host's DHCP client actually reads. Keeping the two
apart is the whole design: a declaration that is rewritten to match
reality has stopped being a declaration.

WHY OPTION 50 AND NOT A ROUTER RESERVATION
-------------------------------------------
Operator ruling, 2026-08-12: 「ホスト側から希望して、DHCP の時にそこが空い
ていれば行くようにしてほしい」 -- the host asks, and DHCP grants it if
free. A reservation table in the router's GUI would also pin the
addresses, and was explicitly rejected (「GUI でやるのは苦痛」): it is
config that exists only inside one appliance, so replacing the router
throws it away and the fleet has to rediscover its own topology by hand.
His stated acceptance test is that swapping the router must not mean
starting from zero, and that "the NAS won't connect" should be answerable
by comparing observed against declared.

THE HONEST LIMIT, STATED WHERE IT CANNOT BE MISSED
---------------------------------------------------
Option 50 is a REQUEST. The server may ignore it, and WILL ignore it when
the address is already leased to another device. So this yields "usually
this address", never "always". A host that asked for ``.171`` and was
granted ``.187`` has a PERFECTLY CORRECT config file and a different
address, and both facts are true at once.

That is why the request lives in ``content`` (checked as ``ok`` /
``absent`` / ``drift`` -- purely "does the file match the declaration?")
while the address the machine actually holds lives in
``verify_command`` (surfaced by ``check --verify`` as an OBSERVATION,
never as a verdict). Reporting a granted-elsewhere address as ``drift``
would accuse a correct configuration of a fault it does not have, and
would train everyone to ignore drift.

WHY ONLY FOUR OF THE NINE HOSTS ARE DECLARED HERE
--------------------------------------------------
Measured on 2026-08-12 by probing every host directly, because the knob
differs per DHCP client and the fleet is not homogeneous. Five machines
have NO supported requested-address mechanism, and writing a file for
them would be worse than writing nothing -- it would be a file that is
present, correct, and read by nothing, with every subsequent ``check``
reporting ``ok``:

* ``ywata-note-win`` -- WSL2 (kernel ``6.18.33.2-microsoft-standard-WSL2``)
  in mirrored-networking mode. No DHCP client runs in Linux at all; the
  ``192.168.11.x`` address on ``eth0`` is mirrored from WINDOWS, which
  owns the lease. ``/etc/dhcp/dhclient.conf`` exists and is read by
  nothing. The knob is on the Windows side.
* ``mba`` -- macOS (Darwin 25.2.0, arm64). The DHCP client is built into
  ``configd``/IPConfiguration; there is no dhclient, no dhcpcd, and no
  supported requested-address setting. macOS re-requests its PREVIOUS
  lease from ``/var/db/dhcpclient/leases`` on its own, which is a
  different mechanism nobody can declare.
* ``scitex-nas-01`` (QNAP QTS, armv7l) and ``scitex-nas-02`` (QNAP QTS,
  x86_64) -- both DO run ISC dhclient, so the knob exists
  (``send dhcp-requested-address``), but ``/`` is a 400 MB RAMDISK
  restored from firmware at every boot (``/etc/config`` ->
  ``/mnt/HDA_ROOT/.config`` is the only persistent store, and
  ``dhclient.conf`` has no twin there). A file written into ``/etc/dhcp``
  survives until the next reboot and then silently vanishes -- a setting
  that decays without ever reporting a fault.
* ``scitex-nas-03`` (UGREEN DXP480T Plus, Debian 12) -- runs ISC dhclient
  on a genuinely persistent overlay filesystem, but
  ``/etc/dhcp/dhclient.conf`` is REGENERATED at every boot by
  ``/usr/ugreen/scripts/dhclient-start`` (its mtime tracks boot time, and
  it carries a machine-generated ``dhcp6.client-id`` derived from the
  MAC). Same outcome as the QNAPs, different cause.

For those five the registry still records the intended address -- intent
that is only written down for the hosts that happen to be configurable is
not a map -- and this module deliberately emits no spec, so ``check``
never claims a compliance it cannot deliver. Giving them predictable
addresses needs a mechanism that does not exist yet (a QNAP
``/etc/config/autorun.sh`` hook, a Windows-side request, a macOS profile),
and that is an operator decision rather than something to guess at.

THE FOUR THAT ARE DECLARED
---------------------------
``scitex-compute-01`` .. ``-04``, all Ubuntu 24.04 running
systemd-networkd under netplan. Verified on the metal, not from memory:
``DHCPv4.RequestAddress`` is present in the ``systemd-networkd`` binary's
own gperf option table on systemd 255, and ``systemd.network(5)`` for that
build says it "is added with it to the initial DHCPDISCOVER message".

The file is a DROP-IN beside netplan's generated unit rather than an edit
to it. netplan rewrites ``/run/systemd/network`` on every apply, so an
edit there is lost; the same man page states that drop-ins under ``/etc``
"take precedence over the main network file wherever located", which is
exactly the ``/run``-main-file, ``/etc``-drop-in arrangement here.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev.host_config import HostConfigSpec

#: Per-host facts a networkd drop-in cannot be written without: the LAN
#: interface, and the netplan-generated unit the drop-in must sit beside.
#: MEASURED per host on 2026-08-12 -- these are not derivable, and they are
#: not uniform (``-03`` and ``-04`` carry 10GbE NICs with different names,
#: and ``-01``/``-02`` genuinely share one interface name while being
#: different machines).
#:
#: The unit name embeds the interface, so this is also the fragile part: if
#: an interface is ever renamed, netplan generates a differently-named unit
#: and the drop-in stops applying while still being byte-correct on disk.
#: ``check`` would keep saying ``ok``. That is precisely what
#: ``verify_command`` is here to catch -- it reports the address the
#: interface actually holds, which stops tracking the declaration the
#: moment the drop-in goes stale.
#: The ONE network file every fleet host gets, byte-for-byte identical.
#:
#: There is no per-host content, and that is the whole point. The previous
#: design keyed a networkd drop-in on a per-host INTERFACE NAME, and this
#: module's own docstring predicted how that ends: "if an interface is ever
#: renamed, netplan generates a differently-named unit and the drop-in stops
#: applying while still being byte-correct on disk. check would keep saying
#: ok." On 2026-09-02 a 10GbE card renumbered compute-01's PCI bus, the
#: onboard NIC became enp9s0, /etc/netplan named enp8s0, netplan matched
#: nothing, every port stayed admin-DOWN, and recovery needed a console.
#:
#: A glob cannot be renamed out of matching. `optional: true` means a port
#: that is absent or unplugged does not hold up boot, so the floor degrades
#: to "whichever ports exist get DHCP" rather than to no network at all.
#:
#: The ADDRESS is not pinned here on purpose. Pinning it would require
#: naming a port, which is the fragility being removed. The pin lives in
#: exactly one place -- the router's MAC-keyed DHCP reservation -- and
#: `requested_address` in the host registry is the LEDGER of what those
#: reservations should be, for the router and for humans, not a thing any
#: host asks for itself. Measured 2026-09-02: every compute host's address
#: is already `dynamic`, so this describes what is running, not a change.
_FLEET_NETPLAN_PATH = "/etc/netplan/99-scitex-fleet.yaml"

_FLEET_NETPLAN_CONTENT = """\
# scitex fleet network floor — written 2026-09-02.
# Keyed to NOTHING positional: not an interface name (moves when a card is
# added/removed — this stranded compute-01 today) and not a MAC (moves when the
# card itself moves to another machine). Any cabled ethernet port gets an
# address, so hardware changes need no config change at all.
network:
  version: 2
  ethernets:
    fleet-en:
      match:
        name: "en*"
      dhcp4: true
      optional: true
"""

#: sha256 of :data:`_FLEET_NETPLAN_CONTENT`, pinned so byte-identity with the
#: DEPLOYED file is a test rather than a hope.
#:
#: These are the exact bytes sac hand-applied to all four compute hosts on
#: 2026-09-02 and reboot-tested on three of them. I could not read the file to
#: confirm it — it is mode 0600 root and this agent is not root — so identity
#: was established two other ways instead: the size matches what `ls -la`
#: reported on compute-04 (466 bytes), and this digest matches the sha256 sac
#: measured on the deployed file.
#:
#: Emitting these bytes VERBATIM means the first `host-config apply` after this
#: lands is a no-op, which is also the cleanest available proof that the
#: generated file and the hand-applied one are the same thing. Change the
#: content and this constant must change with it, deliberately.
_FLEET_NETPLAN_SHA256 = (
    "ddbeeca5be302e5f53f52b3bcbf09f529eba398c39cf386772a05cec90bf9be6"
)


def _netplan_managed_hosts(
    *, hosts_path: str | Path | None = None
) -> tuple[str, ...]:
    """The hosts this floor applies to: the Linux machines netplan runs on.

    Branches on ``kind`` rather than on a hardcoded list, so a new compute
    node converges by being in the registry. The other kinds are excluded
    for measured reasons, not by omission: ``storage`` are NAS appliances
    with their own web-configured networking, ``workstation`` covers a WSL
    machine whose network Windows owns and a macOS laptop, and
    ``hpc-login`` is Spartan, which we do not administer.
    """
    from ._registry import (
        HostRegistryError,
        get_hosts_yaml_path,
        list_hosts,
    )

    records = list_hosts(hosts_path=hosts_path)
    names = tuple(
        sorted(r.name for r in records if r.kind == "compute")
    )
    if not names:
        # REFUSE rather than return (). An empty `hosts` tuple means EVERY
        # host to HostConfigSpec.applies_to, so a registry that has drifted
        # out of listing the compute nodes would not narrow this spec -- it
        # would WIDEN it to every machine in the fleet, writing a netplan
        # file onto NAS appliances and laptops that do not run netplan.
        #
        # MEASURED 2026-09-02 inside an agent container: the resolved
        # registry held 6 records (2 workstation, 3 storage, 1 hpc-login),
        # ZERO compute, and still named the retired `mba` and
        # `ywata-note-win`. So this is the live state of a real vantage
        # point, not a hypothetical.
        raise HostRegistryError(
            f"no `kind: compute` host in the registry at "
            f"{get_hosts_yaml_path(hosts_path)} ({len(records)} record(s): "
            f"{', '.join(sorted(r.name for r in records)) or 'none'}), so the "
            f"network floor cannot be scoped.",
            remediation=(
                "This registry is stale or is the container-local copy. An "
                "agent container resolves ~/.scitex/dev/hosts.yaml under "
                "/home/agent, which is NOT the host registry and omits every "
                "compute node. Point SCITEX_DIR (or hosts_path) at the host "
                "registry before generating host config. Refusing is "
                "deliberate: an empty host tuple would apply this spec to "
                "EVERY machine rather than to none."
            ),
        )
    return names


def provide_dhcp_specs(
    *, hosts_path: str | Path | None = None
) -> list[HostConfigSpec]:
    """Declare the ONE name-independent network floor, identical everywhere.

    Emits a single spec applying to every ``kind: compute`` host, with no
    per-host content at all. That is a deliberate reversal of the previous
    design, which emitted one drop-in PER HOST keyed on that host's
    interface NAME and was wrong for two of the four machines on
    2026-09-02 (both mapped to ``enp8s0``, which exists on no host).

    A file with no per-host fields cannot drift per host, which is
    stronger than a per-host file that happens to be correct today. It
    also makes convergence a checksum compare, so the drift detector is
    the same code path as the writer.
    """
    return [
        HostConfigSpec(
            name="network.fleet-floor",
            path=_FLEET_NETPLAN_PATH,
            content=_FLEET_NETPLAN_CONTENT,
            purpose=(
                "Guarantee every ethernet port asks for DHCP, by GLOB, so a "
                "PCI renumber or NIC swap cannot leave a host with no network "
                "-- the failure that took compute-01 offline for two hours on "
                "2026-09-02 and needed a physical console to recover."
            ),
            provider="scitex-dev",
            hosts=_netplan_managed_hosts(hosts_path=hosts_path),
            mode="0600",
            # `netplan apply` re-reads and re-applies. It does NOT tear the
            # link down when the resulting config is unchanged, which is the
            # normal case for a converged host.
            apply_command="netplan apply",
            # OBSERVATION, and deliberately not a read-back of the file --
            # that would be a tautology. The question this file exists to
            # answer is whether a port actually came up with an address, so
            # ask that. It is also the only check that catches the floor
            # matching nothing, which is exactly how the old design failed
            # while remaining byte-correct on disk.
            verify_command="ip -4 -o addr show | grep -v ' lo '",
            requires_root=True,
        )
    ]


__all__ = ["provide_dhcp_specs"]

# EOF
