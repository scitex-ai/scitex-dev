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

from ._registry import (
    HOST_KINDS,
    HostRecord,
    HostRegistryError,
    UnknownHostError,
    create_default_hosts_yaml,
    find_runner_host,
    get_hosts_yaml_path,
    list_hosts,
    list_requested_addresses,
    list_runner_destinations,
    packaged_default_requested_addresses,
    packaged_default_runner_destinations,
    resolve,
)

# Writes resolve through `._write_target`, NOT through `get_hosts_yaml_path`.
# The read path may legitimately answer with whatever this process can see;
# a write must refuse when it cannot tell which registry the fleet reads.
from ._write_target import candidate_hosts_yamls, resolve_hosts_yaml_for_write

__all__ = [
    "HOST_KINDS",
    "HostRecord",
    "HostRegistryError",
    "UnknownHostError",
    "candidate_hosts_yamls",
    "create_default_hosts_yaml",
    "find_runner_host",
    "get_hosts_yaml_path",
    "list_hosts",
    "list_requested_addresses",
    "list_runner_destinations",
    "packaged_default_requested_addresses",
    "packaged_default_runner_destinations",
    "resolve",
    "resolve_hosts_yaml_for_write",
]

# EOF
