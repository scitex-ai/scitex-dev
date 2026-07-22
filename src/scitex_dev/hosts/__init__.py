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
    get_hosts_yaml_path,
    list_hosts,
    resolve,
)

__all__ = [
    "HOST_KINDS",
    "HostRecord",
    "HostRegistryError",
    "UnknownHostError",
    "create_default_hosts_yaml",
    "get_hosts_yaml_path",
    "list_hosts",
    "resolve",
]

# EOF
