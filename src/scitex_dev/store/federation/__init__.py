#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/store/federation/__init__.py
"""The store federation — leaves declare semantics, scitex-dev owns machinery.

A leaf package registers a provider (``() -> list[StorePlugin]``) under the
``scitex_dev.store.plugins`` entry-point group; scitex-dev owns the
contract, the aggregation and the target resolution, and stays domain-
agnostic. What a leaf declares is the part only it can know — which fields
are immutable, which are last-writer-wins, which append — because a merge
rule guessed here would lose data without raising.

Layout mirrors :mod:`scitex_dev.gate` so the three federations are one
thing to learn:

===================  ========================================================
:mod:`._spec`        the contract (:class:`StorePlugin`). Data only.
:mod:`._discover`    aggregation: the entry-point group, dedup, the seams.
:mod:`._builtin`     scitex-dev's own declarations, via an INTERNAL provider.
:mod:`._resolve`     a declaration -> a :class:`~.._target.StoreTarget`.
===================  ========================================================

This file is a pure re-export façade and holds no logic, so that the import
path a leaf pins never moves when the internals are rearranged.

**Leaves should import from ``scitex_dev.store``, not from here.** The
parent package re-exports every name below; that is the pinned surface, and
this subpackage is an implementation detail of it.
"""

from __future__ import annotations

from ._builtin import provide as provide_builtins
from ._discover import ENTRY_POINT_GROUP, discover_store_plugins, plugin_for
from ._resolve import resolve_target
from ._spec import StorePlugin, StorePluginProvider

__all__ = [
    "ENTRY_POINT_GROUP",
    "StorePlugin",
    "StorePluginProvider",
    "discover_store_plugins",
    "plugin_for",
    "provide_builtins",
    "resolve_target",
]

# EOF
