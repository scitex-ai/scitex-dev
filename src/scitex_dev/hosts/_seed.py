#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The SHIPPED default host-registry seed, and its runner destinations.

scitex-dev owns the single machine registry (see :mod:`scitex_dev.hosts`).
Its canonical seed lives HERE, in package code, so scitex-dev always knows
the fleet's hosts and CI runner destinations regardless of what any host's
on-disk ``~/.scitex/dev/hosts.yaml`` happens to contain.

Two consumers:

* :func:`scitex_dev.hosts.create_default_hosts_yaml` writes
  :data:`_DEFAULT_HOSTS_YAML` verbatim when a host has no registry file yet.
* :func:`packaged_default_runner_destinations` reads the SAME constant to
  give PS-224 a FLOOR to validate against when a host's user-state registry
  contributes no runner destinations (an absent file, or a stale
  pre-``runner_labels`` copy that ``create_default_hosts_yaml`` will not
  overwrite because it only writes when the file is missing).

This module deliberately depends on nothing in ``_registry`` — the parse
below is a small, strict inline read of a TRUSTED constant, kept
dependency-free so ``_registry`` can import the seed string from here
without a cycle.
"""

from __future__ import annotations

# Real host data from the operator's environment — names match the
# established convention already referenced across scitex-dev's own
# skills/docs (ywata-note-win, spartan, nas/nas1/nas2, mba).
_DEFAULT_HOSTS_YAML = """\
# SciTeX host registry — the shared port other scitex-* packages (sac,
# scitex-hub, scitex-storage, ...) resolve through instead of inventing
# their own host config. See `scitex_dev.hosts` for the Python API and
# `scitex-dev host --help` for the CLI.
#
# kind        : one of workstation, hpc-login, storage
# ssh_alias   : the ~/.ssh/config Host alias to reach this machine, or
#               null when the host IS local (no SSH hop needed)
# scitex_root : that HOST's $SCITEX_DIR (may use ~; expanded on that
#               host, not necessarily on the machine reading this file)
# runner_labels : the CI RUNNER DESTINATIONS this machine serves — a LIST
#               OF LABEL SETS, one entry per distinct GitHub Actions
#               self-hosted runner configuration registered from this
#               machine. Absent/empty means "this machine hosts no CI
#               runner". This field is the SOURCE OF TRUTH the PS-224
#               audit rule validates every workflow's `runs-on:` against
#               (see `_cli/audit/_project/_check_runner_destinations.py`).
#
#               Record the EFFECTIVE set, i.e. exactly what
#               `gh api .../actions/runners` reports for that runner —
#               that includes the labels GitHub AUTO-ASSIGNS
#               (`self-hosted`, the OS `Linux`, the arch `X64`) on top of
#               the `--labels` passed at registration. Recording only the
#               `--labels` half would make every workflow that names
#               `Linux`/`X64` look unserved.
#
#               Label sets are one entry PER RUNNER, never a flattened
#               union — a union would green-light a combination no single
#               runner actually offers, and a job whose labels match
#               nothing waits forever (three scheduled runs sat
#               undispatched since 2026-05-15 for exactly this).
#
# CHOOSING LABELS IN A WORKFLOW — breadth matters for QUEUE TIME, and the
# two legal choices below are NOT equivalent:
#   [self-hosted, Linux, X64, spartan-cpu]              -> matches ALL runners
#   [self-hosted, Linux, X64, spartan-cpu, scitex-ci]   -> matches the POOLED
#                                                          subset only
# `spartan-cpu` is carried by every runner; `scitex-ci` only by the pooled
# ones. So asking for `scitex-ci` narrows the eligible set and can queue
# behind the pooled runners even while org-level runners sit idle —
# MEASURED 2026-07-28: a job requesting scitex-ci sat QUEUED 16 minutes;
# the same job on spartan-cpu dispatched immediately. Both PASS PS-224, so
# the gate cannot tell you which you wanted — it validates SERVED-ness, not
# capacity. The org reusables in scitex-ai/.github use spartan-cpu.
# DEFAULT TO `spartan-cpu`; add `scitex-ci` only when a job genuinely needs
# that specific pool.

# requested_address : the LAN address this machine should ASK its DHCP
#               server for (option 50). A REQUEST, NOT A RESERVATION: the
#               server may ignore it, and will ignore it if the address is
#               already leased elsewhere, so it means "usually this
#               address" and never "always". The address a host currently
#               HOLDS is a different fact and is deliberately not recorded
#               here — observe it with `ip -4 -o addr show`, and expect the
#               two to disagree sometimes. That gap is the normal condition
#               of the system, not a fault.
#
#               The FLEET-WIDE map lives in package code as
#               `FLEET_REQUESTED_ADDRESSES` (below) and covers hosts this
#               seed does not yet list; a `requested_address:` here
#               OVERRIDES it for that host. Quote the value — YAML parses a
#               value with fewer than three dots as a number.

hosts:
  ywata-note-win:
    kind: workstation
    ssh_alias: null
    scitex_root: "~/.scitex"
    requested_address: "192.168.11.101"
  spartan:
    kind: hpc-login
    ssh_alias: spartan
    scitex_root: "/data/gpfs/projects/punim0264/ywatanabe/.scitex"
    # Measured 2026-07-24 from the live GitHub Actions API (org
    # `scitex-ai` + repo `scitex-ai/scitex-dev`): four online runners
    # across exactly two distinct effective label sets.
    #   spartan-cpu-org-01 / spartan-cpu-org-02
    #     -> [self-hosted, Linux, X64, spartan-cpu]
    #   spartan-pooled-cpu-01 / spartan-cpu-runner-02
    #     -> [self-hosted, Linux, X64, spartan-cpu, scitex-ci]
    runner_labels:
      - [self-hosted, Linux, X64, spartan-cpu]
      - [self-hosted, Linux, X64, spartan-cpu, scitex-ci]
  nas:
    kind: storage
    ssh_alias: nas
    scitex_root: "~/.scitex"
  nas1:
    kind: storage
    ssh_alias: nas1
    scitex_root: "~/.scitex"
  nas2:
    kind: storage
    ssh_alias: nas2
    scitex_root: "~/.scitex"
  mba:
    kind: workstation
    ssh_alias: mba
    scitex_root: "~/.scitex"
    requested_address: "192.168.11.102"
"""


#: The fleet's DESIRED LAN address map -- what each machine should ASK its
#: DHCP server for (option 50, "Requested IP Address"), keyed by canonical
#: host name.
#:
#: WHY THIS IS A REQUEST AND NOT A RESERVATION
#: -------------------------------------------
#: The obvious way to pin these addresses is a reservation table in the
#: router's web UI. The operator ruled that out on 2026-08-12 for a reason
#: that is about durability rather than taste: config that lives only in a
#: router is lost the day the router is replaced, and the fleet then has to
#: rediscover its own topology by hand. Declared here it is code -- it
#: survives the swap, it diffs, and it can be reviewed.
#:
#: The cost of that choice is honest and permanent: option 50 is a REQUEST.
#: The server may ignore it, and WILL ignore it when the address is already
#: leased to another device. So this map yields "usually this address",
#: never "always", and every consumer must treat a mismatch between this
#: and the observed address as an expected condition rather than a fault.
#:
#: THE LAST OCTET ENCODES THE ROLE, and the scheme is a REPAIR of the
#: operator's original 10N/30N/70N idea: 30N and 70N exceed the 255 ceiling
#: of an octet, so storage moved to 13N and compute to 17N, which keeps his
#: 1/3/7 identifying digit. Approved 2026-08-12.
#:
#:     1NN  workstation (laptops)
#:     13N  storage (NAS)
#:     17N  compute
#:
#: DECLARING AN ADDRESS DOES NOT MEAN THE HOST CAN ASK FOR IT. Only four of
#: these nine machines run a DHCP client with a supported requested-address
#: knob; the other five are declared here because the map is the fleet's
#: record of INTENT, and intent that is only written down for the hosts
#: that happen to be configurable is not a map. See
#: :mod:`scitex_dev._host_config` for the per-host mechanism, and for the
#: measured reason each of the other five has none.
#:
#: Verified free on 2026-08-12 by a TCP-connect + ARP sweep of
#: 192.168.11.0/24 from scitex-compute-04: all nine unoccupied, and all nine
#: inside the span of addresses the router is observably leasing today
#: (.5 through .188), so none of them sits outside the pool.
FLEET_REQUESTED_ADDRESSES: dict[str, str] = {
    # 1NN -- workstations
    "ywata-note-win": "192.168.11.101",
    "mba": "192.168.11.102",
    # 13N -- storage
    "scitex-nas-01": "192.168.11.131",
    "scitex-nas-02": "192.168.11.132",
    "scitex-nas-03": "192.168.11.133",
    # 17N -- compute
    "scitex-compute-01": "192.168.11.171",
    "scitex-compute-02": "192.168.11.172",
    "scitex-compute-03": "192.168.11.173",
    "scitex-compute-04": "192.168.11.174",
}


def packaged_default_requested_addresses() -> dict[str, str]:
    """The DESIRED address map from scitex-dev's SHIPPED declaration.

    Returns a copy of :data:`FLEET_REQUESTED_ADDRESSES` -- a fresh dict per
    call, so a caller that mutates the result cannot rewrite the fleet's
    declaration for the rest of the process.

    Read from PACKAGE CODE rather than from any on-disk ``hosts.yaml``,
    for the same reason :func:`packaged_default_runner_destinations`
    exists: ``create_default_hosts_yaml`` only writes when the file is
    MISSING, so every host that already had a registry before this field
    existed holds a copy with no addresses in it. A host that read its
    local file and found nothing would conclude the fleet has no address
    map -- a silent, per-host disappearance of exactly the record that is
    supposed to survive a router swap.

    Keyed by CANONICAL host name. Several of these machines report a
    different ``socket.gethostname()`` than the name they are registered
    under (the NAS boxes answer ``WATANAS1`` / ``WATANAS2`` /
    ``DXP480TPLUS-994``, and the MacBook ``MacBookAir.lan``), so do NOT
    look up this map by the local hostname on those hosts.
    """
    return dict(FLEET_REQUESTED_ADDRESSES)


def packaged_default_runner_destinations() -> list[tuple[str, frozenset[str]]]:
    """Runner destinations from scitex-dev's SHIPPED default registry seed.

    Same ``(host_name, label_set)`` shape as
    :func:`scitex_dev.hosts.list_runner_destinations`, but read from the
    packaged :data:`_DEFAULT_HOSTS_YAML` constant rather than from any
    on-disk file — one pair per runner label set, sorted by host name.

    PS-224 uses this as its FLOOR: when a host's user-state registry
    contributes no destinations, the rule validates against these shipped
    ones instead of reporting a registry gap, so a stale or empty local
    file can never erase the shipped truth and turn every workflow red for
    a reason unrelated to the workflows. Genuine mismatches still error —
    the floor supplies REAL measured destinations, not a blanket pass.
    """
    import yaml

    data = yaml.safe_load(_DEFAULT_HOSTS_YAML) or {}
    raw_hosts = data.get("hosts") or {}
    out: list[tuple[str, frozenset[str]]] = []
    for name in sorted(raw_hosts):
        record = raw_hosts[name] or {}
        for entry in record.get("runner_labels") or []:
            if not isinstance(entry, list):
                continue
            labels = frozenset(
                str(label).strip() for label in entry if str(label).strip()
            )
            if labels:
                out.append((name, labels))
    return out


# EOF
