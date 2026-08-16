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
# skills/docs (ywata-note-win, spartan, scitex-compute-04,
# scitex-nas-01/02/03, mba).
_DEFAULT_HOSTS_YAML = """\
# SciTeX host registry — the shared port other scitex-* packages (sac,
# scitex-hub, scitex-storage, ...) resolve through instead of inventing
# their own host config. See `scitex_dev.hosts` for the Python API and
# `scitex-dev host --help` for the CLI.
#
# kind        : one of workstation, hpc-login, compute, storage
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
#
# A SECOND KIND OF LABEL — CO-LOCATION, not capacity. `sac-control-plane`
# (scitex-compute-04, below) does not name a faster or bigger machine; it
# names THE machine a job must run ON to reach a loopback-bound service.
# Narrowing for capacity is a queue-time trade you can undo; narrowing for
# co-location is a correctness requirement you cannot. Read that entry's
# comment before pinning anything to it — the cost is that the job becomes
# exactly as available as one machine.

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
    # MEASURED 2026-08-15 from scitex-compute-04, BOTH directions, BatchMode
    # (key-based, no prompt, no agent forwarding):
    #     compute-04 -> ywata-note-win   `hostname` -> ywata-note-win
    #     ywata-note-win -> compute-04   `hostname` -> scitex-compute-04
    #
    # It read `null` until then, and `null` is the legend's "the host IS
    # local" — true when this file was authored ON the laptop, and an
    # assertion that THE LAPTOP IS THIS MACHINE everywhere else. Locality is a
    # relation between a host and whoever is asking, so a shared registry
    # cannot hold it in a field (dotfiles' report; PR #580 redefines the
    # absent value as "no alias recorded"). Recording the MEASURED alias makes
    # this host's answer correct under either reading, which is why it does
    # not wait for that change.
    #
    # It is load-bearing now: the cross-host doorbell relay
    # (`scitex_dev.store._relay_ssh`) rings each peer over ssh, and the
    # operator's stated acceptance test for push-driven sync is DM delivery
    # between this laptop and compute-04, both ways. A peer with no alias is
    # not reachable, and the relay REFUSES such a peer rather than skipping
    # it — so an unrecorded alias here is a loud failure, not a silent one.
    ssh_alias: ywata-note-win
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
  scitex-compute-04:
    kind: compute
    ssh_alias: scitex-compute-04
    scitex_root: "~/.scitex"
    # Measured 2026-08-12, from BOTH ends: the live GitHub Actions API (org
    # `scitex-ai`) for the labels, and `~/actions-runner-org/.runner` ON the
    # machine for which machine the runner is. One runner:
    #   agentName scitex-04-org-cpu-01  (on host `scitex-compute-04`)
    #     -> [self-hosted, Linux, X64, scitex-org-cpu, sac-control-plane]
    #
    # WHAT `sac-control-plane` MEANS — the registry has no field for a
    # destination's MEANING, only its labels, so it is recorded here. The
    # label is a CO-LOCATION claim, not a capability tier: this is the one
    # org runner that shares a machine with the sac control plane. Measured
    # on the bare host the same day, both services bind LOOPBACK:
    #   sac listen   LISTEN 127.0.0.1:7878
    #   card store   LISTEN 127.0.0.1:55432   (postgres)
    # A job that must reach either therefore has to EXECUTE on this machine.
    # On any other runner `127.0.0.1` is a different machine's daemon and a
    # different postgres, so the call is delivered to nobody and the write is
    # recorded nowhere — while the job still reports success. That is why the
    # pin exists (sac ADR-0024 assumed the runners were co-located; they are
    # four runners on four machines, and only this one is).
    #
    # WHAT IT COSTS — anything pinned to `sac-control-plane` is exactly as
    # available as this ONE machine. It does not fail over; if the machine is
    # down the job queues, and PS-224 will still pass it, because this gate
    # validates SERVED-ness and not capacity. Pin ONLY work that genuinely
    # needs loopback access to the control plane. The pin becomes unnecessary
    # the day those services stop binding loopback-only — that is a policy
    # decision, not something to engineer around.
    #
    # THE POOL IS NOW COMPLETE — the three siblings below were added
    # 2026-08-15. This comment used to end "UNDER-REPORTS the pool by three",
    # and that under-report was not free: it meant a reader of this file could
    # see `scitex-org-cpu` as legal while believing exactly one machine served
    # it, at a moment when it was the ONLY pool still online.
    runner_labels:
      - [self-hosted, Linux, X64, scitex-org-cpu, sac-control-plane]
    # `scitex-04-dotfiles-01`, registered to `ywatanabe1989/.dotfiles`, is a
    # SECOND runner on this same machine. It is recorded because this field is
    # one entry PER RUNNER, and omitting a repo-scoped runner would make a
    # workflow that legitimately names `dotfiles-ci` read as unserved.
      - [self-hosted, Linux, X64, dotfiles-ci, scitex-local-cpu]
  scitex-compute-01:
    kind: compute
    ssh_alias: scitex-compute-01
    scitex_root: "~/.scitex"
    # Measured 2026-08-15 from BOTH ends, the same discipline as
    # scitex-compute-04 above: `~/actions-runner*/.runner` ON the machine for
    # WHICH runner lives WHERE, and the GitHub Actions API for the labels.
    # Neither half is inferred from the naming pattern — `scitex-01-*` living
    # on `scitex-compute-01` is exactly the kind of correspondence that is
    # usually true and occasionally not.
    #   agentName scitex-01-org-cpu-01  (org scitex-ai)
    #     -> [self-hosted, Linux, X64, scitex-org-cpu]
    #   agentName scitex-01-cpu-01      (repo scitex-ai/scitex-agent-container)
    #     -> [self-hosted, Linux, X64, scitex-ci, scitex-local-cpu]
    #
    # THAT SECOND ENTRY IS WHY SCOPE BELONGS IN THIS FILE'S REASONING. On
    # 2026-08-15 every ORG runner carrying `scitex-ci` was offline, and it was
    # briefly reported fleet-wide that the label was dead. It was not: this
    # repo-scoped runner carried it and was online. A destination's liveness is
    # a question about a SCOPE, not about a label.
    runner_labels:
      - [self-hosted, Linux, X64, scitex-org-cpu]
      - [self-hosted, Linux, X64, scitex-ci, scitex-local-cpu]
  scitex-compute-02:
    kind: compute
    ssh_alias: scitex-compute-02
    scitex_root: "~/.scitex"
    # Measured 2026-08-15. `~/actions-runner*/.runner` also records
    # `scitex-02-cpu-01` (repo scitex-ai/scitex-agent-container) on this
    # machine, but that runner is NOT in the repo's registered runner list, so
    # its label set is unknown and it is deliberately NOT recorded. A leftover
    # config file on disk is not a registered destination, and inventing a
    # label set for it from its sibling's would be exactly the pattern-guess
    # this file refuses elsewhere.
    #   agentName scitex-02-org-cpu-01  (org scitex-ai)
    #     -> [self-hosted, Linux, X64, scitex-org-cpu]
    runner_labels:
      - [self-hosted, Linux, X64, scitex-org-cpu]
  scitex-compute-03:
    kind: compute
    ssh_alias: scitex-compute-03
    scitex_root: "~/.scitex"
    # Measured 2026-08-15. Same caveat as scitex-compute-02 about the
    # unregistered `scitex-03-cpu-01` config on disk.
    #   agentName scitex-03-org-cpu-01  (org scitex-ai)
    #     -> [self-hosted, Linux, X64, scitex-org-cpu]
    runner_labels:
      - [self-hosted, Linux, X64, scitex-org-cpu]
  # RENAMED 2026-08-07. The old aliases `nas` / `nas1` / `nas2` are RETIRED:
  # they resolve to nothing on purpose, printing the successor name and
  # exiting 255. Serving them from here made this registry hand out routes
  # that were decommissioned four days earlier — an SSoT for discovery whose
  # route data is stale is worse than no registry, because consumers trust it.
  #
  # Reported by scitex-storage 2026-08-11 with the consumption measured, from
  # ~/.ssh/retired-alias-hits.log:
  #     1074  old=nas   new=scitex-nas-03   (scitex-orochi host-liveness-probe,
  #                                          5-minute timer, still firing)
  #       83  old=nas2  new=scitex-nas-02   (sac push-hub-cred)
  #        4  old=nas1  new=scitex-nas-01
  #
  # The successors are NOT inferred. The retirement stub records `old=X new=Y`
  # on every hit, so the mapping below is read from the mechanism that owns
  # it rather than guessed from the naming pattern — which matters because
  # `nas` -> `scitex-nas-03` is exactly the pair a pattern would get wrong.
  #
  # The old names stay as `aliases:` DELIBERATELY, and the split is the whole
  # point: `ssh_alias` is the ROUTE (must be a name ssh can still reach —
  # that is the bug being fixed), `aliases` are LOOKUP KEYS (names a caller
  # may still pass to `resolve()`). A caller asking for `nas` is not wrong,
  # it is using the name the fleet used until four days ago; it should get
  # the successor record, not a KeyError. Dropping them would convert a
  # stale-route bug into a resolution failure for every such caller.
  scitex-nas-01:
    kind: storage
    ssh_alias: scitex-nas-01
    aliases: [nas1, nas-01]
    scitex_root: "~/.scitex"
  scitex-nas-02:
    kind: storage
    ssh_alias: scitex-nas-02
    aliases: [nas2, nas-02]
    scitex_root: "~/.scitex"
  scitex-nas-03:
    kind: storage
    ssh_alias: scitex-nas-03
    aliases: [nas, nas3, nas-03]
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
