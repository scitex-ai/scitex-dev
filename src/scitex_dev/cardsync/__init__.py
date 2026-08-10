#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex_dev.cardsync`` — reconcile card stores that predate the primitive.

A BRIDGE. It should be deleted, not extended.

The fleet's card store is not built on :mod:`scitex_dev.store`: it has no
oplog, so :func:`scitex_dev.store.replay` has nothing to replay. Three hosts
each hold a full copy and drift apart with nothing reconciling them. On
2026-08-10 that reached 2,341 differing rows and was closed by hand.

This package does the only thing possible from outside a foreign schema —
compare end states and copy the winner — and that is strictly weaker than an
oplog. Comparing states cannot tell "never sent to me" from "removed there";
both read as absence. So :func:`~._decide.decide` NEVER treats absence as
deletion, and the package offers no delete verb at all. When scitex-cards
adopts the primitive, delete this.

The interesting part is :mod:`._decide`: one pure function, three-valued,
that decides which side of a disagreement wins and records why. Everything
else is I/O.
"""

from __future__ import annotations

from ._decide import Side, Verdict, decide

__all__ = ["Side", "Verdict", "decide"]

# EOF
