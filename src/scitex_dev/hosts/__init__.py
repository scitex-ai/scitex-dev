#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex_dev.hosts`` — the SciTeX-wide host registry (Ports & Adapters).

**This module is the port.** It answers, once, ecosystem-wide: *where is
host X, and what's its ``~/.scitex`` root path?* Other packages —
notably ``sac`` (scitex-agent-container, which currently owns this ad
hoc in ``~/.scitex/agent-container/config.yaml``), ``scitex-hub``, and
``scitex-storage`` — are the adapters: they should call
:func:`resolve` / :func:`list_hosts` here rather than parsing their own
host config or hardcoding a host-specific absolute path.

Why this exists (the incident that motivated it)
--------------------------------------------------
A host-specific absolute path
(``/data/gpfs/projects/punim0264/ywatanabe/.scitex``, Spartan-only) was
committed as a literal git-tracked SYMLINK at ``src/.scitex`` in the
shared dotfiles repo. Every non-Spartan host that checks out that
commit gets a DANGLING symlink at ``~/.scitex`` — the path where the
ENTIRE fleet's config/runtime state lives — which already silently
broke config delivery to a NAS host. Resolving host paths through this
registry instead of a hardcoded/symlinked path is the fix: a NAS host
never needs to know Spartan's GPFS path, and Spartan's path can change
without touching every other host's checkout.

Usage
-----
::

    from scitex_dev.hosts import resolve, list_hosts

    spartan = resolve("spartan")
    print(spartan.scitex_root)        # raw string, may contain ~
    print(spartan.scitex_root_path)   # expanded Path (see the property
                                       # docstring for the "whose home
                                       # directory" caveat)

    for host in list_hosts():
        print(host.name, host.kind, host.ssh_alias)

Runner destinations
-------------------
The registry is also the SOURCE OF TRUTH for legal CI runner
destinations. Each machine records the label sets its self-hosted GitHub
Actions runners serve under ``runner_labels:``, and
:func:`find_runner_host` answers "can anything in the fleet pick up a job
that asked for these labels?"::

    from scitex_dev.hosts import find_runner_host

    find_runner_host(["self-hosted", "Linux", "X64", "scitex-ci"])  # -> spartan
    find_runner_host(["self-hosted", "scitex-agentic"])             # -> None

A ``None`` is not a capacity problem — it means NO machine advertises
that label set, so the job is undeliverable and queues forever. That is
a real, measured failure mode: three scheduled runs (scitex-io,
scitex-hub, scitex-writer) sat with ``updated_at == created_at`` from
2026-05-15 while runners sat online and idle, because they named a
destination nothing served. The PS-224 audit rule turns that into a
pre-merge ERROR — see
``_cli/audit/_project/_check_runner_destinations.py``.

Connectivity — where a host IS, not just where its files are
-------------------------------------------------------------
Each record also carries a :class:`~._connectivity.HostConnectivity`: the
OBSERVED LAN address, the DHCP RESERVATION (a separate fact — leases go
unrenewed), the off-LAN ``net`` route, the MAC, the ssh host-key
fingerprint, the identity-file PATH, and ``last_seen``. Every field is
optional, so a registry written before this existed parses unchanged.

Four things consume it, and each answers a question a config file cannot:

* :func:`render_ssh_config` — generate ``<name>`` (LAN) and ``<name>-net``
  (off-LAN) stanzas into a marked managed block. Never deletes an entry for
  being unreachable; ages ``last_seen`` instead.
* :func:`check_matrix` — probe the N*(N-1) ORDERED pairs per transport and
  report the DENOMINATOR, so a sweep that mostly did not run cannot read as
  a pass.
* :func:`check_ssh_config` — ask ``ssh -G`` what actually wins, and whether
  the key a stanza NAMES exists. This is the fault that took the mesh down
  on 2026-08-13.
* :func:`corroborate` — MAC, host-key continuity and a live hostname probe.
  All three must agree before an address may be rewritten; anything less is
  ``insufficient``, never a pass.

**No private key material is ever stored, transmitted, or accepted** — only
public facts (addresses, MACs, fingerprints, paths). The parser refuses a
PEM header or a secret-shaped field name outright.

Backed by ``~/.scitex/dev/hosts.yaml`` (a DATA/STATE store — see
``01_ecosystem/12_local-state-resolution.md`` — resolved via
``local_state.user_path()`` so it is never project-shadowed), seeded
with the operator's known hosts on first use. CLI surface:
``scitex-dev host list|show|resolve``.

This PR ships only the registry itself. Migrating sac / scitex-hub /
scitex-storage's own code to consume it is explicitly out of scope —
separate follow-up work in each of those packages.
"""

from __future__ import annotations

from ._connectivity import (
    NET_SUFFIX,
    TRANSPORTS,
    HostConnectivity,
    NetRoute,
    net_name,
)
from ._corroborate import (
    REQUIRED_SIGNALS,
    VERDICT_CONFLICT,
    VERDICT_CORROBORATED,
    VERDICT_INSUFFICIENT,
    Corroboration,
    Signal,
    corroborate,
)
from ._effective import (
    AliasCheck,
    Finding,
    SshConfigReport,
    check_ssh_config,
    effective_config,
    parse_ssh_g,
)
from ._probe import MatrixResult, PairProbe, check_matrix, local_host_name
from ._registry import (
    HOST_KINDS,
    HostRecord,
    HostRegistryError,
    UnknownHostError,
    create_default_hosts_yaml,
    find_runner_host,
    get_hosts_yaml_path,
    list_hosts,
    list_runner_destinations,
    packaged_default_runner_destinations,
    resolve,
)
from ._run import CommandResult, run_command
from ._ssh_config import (
    BEGIN_MARKER,
    END_MARKER,
    ManagedWrite,
    default_managed_path,
    render_ssh_config,
    write_managed,
)

# Writes resolve through `._write_target`, NOT through `get_hosts_yaml_path`.
# The read path may legitimately answer with whatever this process can see;
# a write must refuse when it cannot tell which registry the fleet reads.
from ._write_target import candidate_hosts_yamls, resolve_hosts_yaml_for_write

__all__ = [
    "BEGIN_MARKER",
    "END_MARKER",
    "HOST_KINDS",
    "NET_SUFFIX",
    "REQUIRED_SIGNALS",
    "TRANSPORTS",
    "VERDICT_CONFLICT",
    "VERDICT_CORROBORATED",
    "VERDICT_INSUFFICIENT",
    "AliasCheck",
    "CommandResult",
    "Corroboration",
    "Finding",
    "HostConnectivity",
    "HostRecord",
    "HostRegistryError",
    "ManagedWrite",
    "MatrixResult",
    "NetRoute",
    "PairProbe",
    "Signal",
    "SshConfigReport",
    "UnknownHostError",
    "candidate_hosts_yamls",
    "check_matrix",
    "check_ssh_config",
    "corroborate",
    "create_default_hosts_yaml",
    "default_managed_path",
    "effective_config",
    "find_runner_host",
    "get_hosts_yaml_path",
    "list_hosts",
    "list_runner_destinations",
    "local_host_name",
    "net_name",
    "packaged_default_runner_destinations",
    "parse_ssh_g",
    "render_ssh_config",
    "resolve",
    "resolve_hosts_yaml_for_write",
    "run_command",
    "write_managed",
]

# EOF
