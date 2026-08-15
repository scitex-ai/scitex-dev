#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/store/federation/_builtin.py
"""scitex-dev's OWN store declarations, through an internal provider.

Why not an entry point
----------------------
scitex-dev is a LEAF of this federation, not a privileged parent — it owns
the machinery AND happens to own one store, and those are different hats.
But it must not register itself in the group it also reads. Discovery would
then walk this package's own metadata to find this package, which is a
self-recursion with two concrete costs:

* the built-in becomes conditional on scitex-dev being pip-INSTALLED with
  its ``.dist-info`` present, so a source checkout on ``PYTHONPATH`` loses
  its own store while every leaf keeps theirs — the failure would look like
  a scitex-dev bug from every direction except the true one;
* a leaf that also vendors the declaration would double-count it, and
  first-wins dedup would silently pick whichever the entry-point walk
  emitted first.

An internal provider has neither problem: it is always available, exactly
once, and :func:`~._discover.discover_store_plugins` merges it FIRST so
scitex-dev's own semantics cannot be overridden by an installed leaf
claiming the same name.

The one built-in
----------------
``status_exchanges`` — :mod:`scitex_dev.status`'s exchange ledger, one row
per A->B exchange. It is a genuine store rather than a placeholder, which
matters: a federation whose only built-in is a stub proves the seam exists
but never that it carries anything.
"""

from __future__ import annotations

from .._policy import WriterPolicy
from ._spec import StorePlugin

__all__ = ["provide"]


def provide() -> "list[StorePlugin]":
    """scitex-dev's own store plugins.

    Built on call rather than at import, for the reason
    :func:`scitex_dev.status.ledger_schema` is: importing the federation
    contract must not drag in the status package for a caller that only
    wanted to know which stores exist by name.
    """
    from ...status._ledger import LEDGER_TABLE, ledger_schema

    return [
        StorePlugin(
            name=LEDGER_TABLE,
            pkg="dev",
            schema=ledger_schema(),
            # An exchange is written by BOTH ends: the initiator opens it and
            # the responder concludes it. SINGLE_WRITER would reject the
            # completion — the exact half-recorded exchange the ledger exists
            # to make findable.
            writer_policy=WriterPolicy.MULTI_WRITER,
            provider="scitex-dev",
            description=(
                "One row per A->B exchange: who asked, who answered, the "
                "status code verbatim, and whether it was ever concluded."
            ),
        ),
    ]

# EOF
