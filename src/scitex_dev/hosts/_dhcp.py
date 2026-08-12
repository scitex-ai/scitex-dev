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
_NETWORKD_HOSTS: dict[str, str] = {
    "scitex-compute-01": "enp8s0",
    "scitex-compute-02": "enp8s0",
    "scitex-compute-03": "enp35s0f0",
    "scitex-compute-04": "enp3s0f0",
}

#: Name of the drop-in file inside ``<unit>.network.d/``. The ``50-``
#: prefix leaves room either side: netplan's own passthrough drop-ins (if
#: it ever grows one) sort earlier, and a deliberate local override can be
#: added as ``60-`` without editing a scitex-managed file.
_DROP_IN_BASENAME = "50-scitex-requested-address.conf"


def _drop_in_body(host: str, iface: str, address: str) -> str:
    """Render the networkd drop-in for one host.

    The banner is long on purpose. This file is read by whoever is
    debugging why a machine is not on the address they expected, and the
    single most useful thing it can tell them is that the address was only
    ever a request -- otherwise the obvious conclusion is that the config
    is broken, and the obvious next move is to "fix" it by hand.
    """
    return f"""\
# Managed by scitex-dev. Do not edit by hand -- edits show up as DRIFT in
# `scitex-dev ecosystem host-config check` and are deliberately NOT
# auto-reverted, so a hand edit will sit there being reported until
# someone decides which side is right.
#
# Declared by HostConfigSpec "dhcp.requested-address.{host}"
# in scitex_dev/hosts/_dhcp.py. The ADDRESS is not declared there: it
# comes from the fleet host registry (scitex_dev.hosts), which is the
# single source of truth. To move this host, change the registry.
#
# THIS IS A REQUEST, NOT A RESERVATION. DHCP option 50 asks the server for
# an address; the server may refuse, and WILL refuse if {address}
# is already leased to another device. So this means "usually
# {address}" and never "always". If this machine is on some other
# address, that is not necessarily a fault -- compare
# `ip -4 -o addr show {iface}` against this file rather than assuming
# they agree. The gap between the two is the normal condition of a
# request-based scheme, which is why it is declared here rather than
# reserved in the router.
#
# IT ALSO DOES NOT TAKE EFFECT IMMEDIATELY. Option 50 rides on the initial
# DHCPDISCOVER, and a lease RENEWAL keeps the current address. So applying
# this file changes nothing until the next discover -- a reboot, or a lost
# lease. `networkctl reload` makes networkd read the file; it deliberately
# does not yank the address out from under whoever is logged in.
#
# WHY A DROP-IN: netplan regenerates /run/systemd/network on every apply,
# so an edit to its unit is lost. systemd.network(5) states drop-ins under
# /etc "take precedence over the main network file wherever located".
[DHCPv4]
RequestAddress={address}
"""


def provide_dhcp_specs() -> list[HostConfigSpec]:
    """Declare the requested-address drop-in for every host that can use one.

    Reads the addresses from the host registry rather than repeating them,
    so there is exactly one place to change when a machine moves.

    Emits one spec PER HOST. Two of them (``-01`` and ``-02``) resolve to
    the SAME path, because those machines happen to share an interface
    name -- that is not a collision, it is disjoint ``hosts`` tuples
    landing on one filename, and ``discover_host_config`` treats it as a
    conflict only when two declarations could both apply to one machine.

    A host in the registry map with no entry in :data:`_NETWORKD_HOSTS`
    yields NO spec, deliberately. See the module docstring for the five
    machines in that position and the measured reason for each.
    """
    from ._seed import packaged_default_requested_addresses

    addresses = packaged_default_requested_addresses()
    specs: list[HostConfigSpec] = []
    for host in sorted(_NETWORKD_HOSTS):
        address = addresses.get(host)
        if not address:
            # The registry stopped declaring an address for a host we know
            # how to configure. Skip rather than invent one -- a guessed
            # address is how a machine lands on top of another.
            continue
        iface = _NETWORKD_HOSTS[host]
        specs.append(
            HostConfigSpec(
                name=f"dhcp.requested-address.{host}",
                path=(
                    f"/etc/systemd/network/10-netplan-{iface}.network.d/"
                    f"{_DROP_IN_BASENAME}"
                ),
                content=_drop_in_body(host, iface, address),
                purpose=(
                    f"Ask DHCP for {address} so {host} keeps a predictable "
                    f"LAN address without a router-side reservation that a "
                    f"router swap would discard (a request, not a "
                    f"guarantee -- the server may refuse it)."
                ),
                provider="scitex-dev",
                hosts=(host,),
                mode="0644",
                # Makes networkd re-read the drop-in. Deliberately NOT
                # `networkctl reconfigure`, which re-runs DHCP and would
                # move the address -- and cut the ssh session doing the
                # applying -- the instant this is applied.
                apply_command="networkctl reload",
                # OBSERVATION, not config. Reading the file back would be
                # a tautology, and the interesting question is precisely
                # the one the file cannot answer: what did the server
                # actually grant? This is also the only thing that catches
                # a drop-in gone stale after an interface rename, where
                # the file is still byte-correct and applies to nothing.
                verify_command=f"ip -4 -o addr show {iface}",
                requires_root=True,
                # Without networkd, a file under /etc/systemd/network is
                # read by nothing -- present, correct, and inert, with
                # `check` reporting ok forever.
                requires_command="networkctl",
            )
        )
    return specs


__all__ = ["provide_dhcp_specs"]

# EOF
