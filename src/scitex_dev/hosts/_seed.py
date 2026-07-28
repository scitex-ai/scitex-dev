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
