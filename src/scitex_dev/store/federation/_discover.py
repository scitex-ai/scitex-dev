#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/store/federation/_discover.py
"""Aggregate every :class:`~._spec.StorePlugin` declared in this environment.

Mirrors ``scitex_dev.gate.discover_gate_checks`` and
``scitex_dev.system_deps.discover_system_deps``, deliberately: three
federations with three different discovery contracts would be three things
to learn. ``scitex_dev.jobs.discover_jobs`` is the OLDEST copy and lacks the
``include_entry_points`` seam — it is NOT the template here; its tests can
only assert set-membership because of that omission.

The determinism guarantee
-------------------------
``include_entry_points=False`` skips the entry-point walk, so a test may
assert an EXACT list rather than a membership. With the flag left ``True``
the result depends on which packages happen to be installed in the running
environment, and an exact-list assertion would pass on the author's machine
and fail in CI — or, worse, the reverse.

``include_builtins`` is the matching seam for scitex-dev's OWN declarations
(:mod:`._builtin`). Those arrive through an internal provider and never
through an entry point: scitex-dev is a LEAF of this federation, not a
privileged parent, and registering itself in a group it also reads would
have discovery load scitex-dev's metadata to find scitex-dev.

Why an empty federation is a message, not a value
-------------------------------------------------
An installed-but-unregistered leaf and a typo'd store name produce the same
empty result, and :func:`plugin_for` therefore distinguishes them in prose.
That is the module's whole posture: a read that comes back empty must be
able to say WHY it is empty, because every failure of 2026-08-11 was a
truthful empty answer about the wrong thing.
"""

from __future__ import annotations

import logging
import sys

from .._errors import StoreError
from ._spec import StorePlugin, StorePluginProvider

__all__ = ["ENTRY_POINT_GROUP", "discover_store_plugins", "plugin_for"]

_logger = logging.getLogger(__name__)

#: Entry-point group every leaf registers its store-semantics provider
#: under. Named for the linter federation's precedent
#: (``scitex_dev.linter.plugins``), which is the other place a leaf
#: declares its own rules for a keystone-owned engine to execute.
#:
#: PINNED BY TEST. Renaming it orphans every installed leaf silently —
#: discovery would simply find nothing and report an empty federation,
#: which is indistinguishable from "no leaf has adopted the store yet".
ENTRY_POINT_GROUP = "scitex_dev.store.plugins"


def _iter_entry_points(group: str):
    """Yield entry points for ``group``, compatible with Python 3.9+."""
    from importlib.metadata import entry_points

    if sys.version_info >= (3, 10):
        return entry_points(group=group)
    return entry_points().get(group, [])


def _make_ep_provider(ep) -> StorePluginProvider:
    """Wrap an entry point into a provider callable returning plugins."""

    def _provider() -> "list[StorePlugin]":
        get_plugins = ep.load()
        return list(get_plugins())

    _provider.__name__ = f"entry_point:{getattr(ep, 'name', '?')}"
    return _provider


def discover_store_plugins(
    *,
    extra_providers: "list[StorePluginProvider] | None" = None,
    include_entry_points: bool = True,
    include_builtins: bool = True,
) -> "list[StorePlugin]":
    """Every store declaration installed in this environment.

    ``include_entry_points=False`` is the unit-test isolation seam: with
    ``include_builtins=False`` alongside it, only ``extra_providers`` are
    aggregated, so exact-list assertions stay valid regardless of which real
    leaves are installed in the running env.

    Dedup is by ``name``, FIRST WINS in provider order (built-ins, then
    entry points, then ``extra_providers``). The returned list is sorted by
    name so two runs over the same environment produce the same order.

    A provider that raises is SKIPPED with a warning rather than taking the
    federation down. One leaf shipping a broken declaration must not stop
    every other leaf's store from resolving — but it must not pass
    unnoticed either, hence the warning with a traceback.
    """
    providers: "list[StorePluginProvider]" = []
    if include_builtins:
        from ._builtin import provide as _builtin_provide

        providers.append(_builtin_provide)
    if include_entry_points:
        for ep in _iter_entry_points(ENTRY_POINT_GROUP):
            providers.append(_make_ep_provider(ep))
    if extra_providers:
        providers.extend(extra_providers)

    by_name: "dict[str, StorePlugin]" = {}
    for provider in providers:
        try:
            declared = provider()
        except Exception:
            _logger.warning(
                "Skipping store plugins from provider %r: it raised.",
                getattr(provider, "__name__", provider),
                exc_info=True,
            )
            continue
        for plugin in declared:
            if not isinstance(plugin, StorePlugin):
                _logger.warning(
                    "Ignoring %r from provider %r: a store plugin provider "
                    "must return StorePlugin instances.",
                    type(plugin).__name__,
                    getattr(provider, "__name__", provider),
                )
                continue
            if plugin.name in by_name:
                existing = by_name[plugin.name]
                if existing.pkg != plugin.pkg or existing.provider != plugin.provider:
                    _logger.warning(
                        "Two packages declare store %r: %s (pkg=%s, kept) and "
                        "%s (pkg=%s, ignored). Only one may own a store's "
                        "merge semantics.",
                        plugin.name,
                        existing.provider,
                        existing.pkg,
                        plugin.provider,
                        plugin.pkg,
                    )
                continue
            by_name[plugin.name] = plugin

    return [by_name[name] for name in sorted(by_name)]


def plugin_for(
    name: str,
    *,
    extra_providers: "list[StorePluginProvider] | None" = None,
    include_entry_points: bool = True,
    include_builtins: bool = True,
) -> StorePlugin:
    """The plugin declaring store ``name``, or a pointed error.

    Raises :class:`~.._errors.StoreError` naming every store the federation
    DID find. An empty federation is called out separately: "no leaf has
    declared a store" and "that particular store is not declared" have
    different causes — a missing install versus a typo — and one message
    covering both sends the reader looking in the wrong place.
    """
    found = discover_store_plugins(
        extra_providers=extra_providers,
        include_entry_points=include_entry_points,
        include_builtins=include_builtins,
    )
    for plugin in found:
        if plugin.name == name:
            return plugin

    if not found:
        raise StoreError(
            f"No store named {name!r}: the federation is EMPTY — no "
            "installed package declares a store at all.\n"
            f"A leaf declares one with an entry point in group "
            f"{ENTRY_POINT_GROUP!r} loading to a callable that returns "
            "list[StorePlugin]. If the owning package IS installed, it was "
            "most likely installed without its metadata (a bare "
            "PYTHONPATH addition registers no entry points) — reinstall it "
            "with pip so the .dist-info is present."
        )
    raise StoreError(
        f"No store named {name!r}. Declared stores: "
        f"{[p.name for p in found]}.\n"
        f"Register one under entry-point group {ENTRY_POINT_GROUP!r}."
    )

# EOF
