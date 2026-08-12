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

hosts:
  ywata-note-win:
    kind: workstation
    ssh_alias: null
    scitex_root: "~/.scitex"
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
    # NOT THE WHOLE POOL: `scitex-01/02/03-org-cpu-01` also serve
    # [self-hosted, Linux, X64, scitex-org-cpu] (scitex-01 offline as of the
    # measurement). Their machines are not registered here yet, so the
    # `scitex-org-cpu` destination is legal on the strength of this single
    # entry and UNDER-REPORTS the pool by three. Legality is right; capacity
    # read off this file would not be.
    runner_labels:
      - [self-hosted, Linux, X64, scitex-org-cpu, sac-control-plane]
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
"""


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
