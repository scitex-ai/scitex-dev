#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/store/federation/_resolve.py
"""Turn a declaration into a target: WHERE the leaf's store actually lives.

The counterpart to :mod:`._discover` — discovery says which stores exist,
this says where one of them is — and the reason the federation exists at
all rather than each leaf simply constructing a
:class:`~.._store.Store` for itself.

**A leaf does not resolve its own store target.** That is the load-bearing
sentence of this module. On 2026-08-11 ``scitex-compute-04`` reached two
different Postgres instances that both answered to one ``store_uuid``,
because target resolution lived in the CONSUMER and two consumers resolved
differently — one to the host's Postgres on ``:55432``, one through an SSH
tunnel presented as ``127.0.0.1:5442`` to the NAS's. Both were "correct" by
their own configuration. 404 cards ended up on one and 146 on the other,
and every read, write and ack on both reported success.

Resolution centralised here cannot disagree with itself.
"""

from __future__ import annotations

from .._target import StoreTarget
from ._spec import StorePlugin

__all__ = ["resolve_target"]


def resolve_target(plugin: StorePlugin) -> StoreTarget:
    """WHERE ``plugin``'s store lives on this host.

    Goes through :func:`~.._host.host_store`, which has exactly two steps
    (``SCITEX_STORE_DSN`` or the per-host Postgres) and deliberately NO
    SQLite fallback: a host whose Postgres is down must fail loudly rather
    than start writing to a private local file that shares nothing. A
    fallback here would reproduce the 2026-08-09 shape by design — a write
    that succeeds locally while reaching nobody.
    """
    from .._host import host_store

    return host_store(pkg=plugin.pkg, name=plugin.name)

# EOF
