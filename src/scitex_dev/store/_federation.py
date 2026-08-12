#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The store federation — leaves declare semantics, scitex-dev owns machinery.

The division of labour, and why it is this way round
----------------------------------------------------
A leaf package knows things scitex-dev cannot: that a card's ``status`` is
last-writer-wins but its ``created_at`` is immutable, that ``comments`` is
an append-only collection and ``last_activity`` must never move backwards.
Those are DOMAIN facts. Nobody outside scitex-cards can state them, and a
default guessed here would be wrong silently — see :mod:`._policy` for why
that is the one thing this primitive refuses to do.

Everything else is machinery: the oplog, the clock, the cursors, the gap
assertion, and — critically — WHERE THE STORE IS. A leaf declares a
:class:`StorePlugin`; it does not resolve its own target.

That last point is the whole reason this module exists rather than each
leaf simply constructing a :class:`~._store.Store` for itself. On
2026-08-11 ``scitex-compute-04`` reached two different Postgres instances
that both answered to one ``store_uuid``, because target resolution lived
in the consumer and two consumers resolved differently. Resolution
centralised here cannot disagree with itself.

Mirrors the shape of ``scitex_dev.gate.discover_gate_checks`` and
``scitex_dev.system_deps.discover_system_deps``, deliberately: three
federations with three different discovery contracts would be three things
to learn. ``scitex_dev.jobs.discover_jobs`` is the OLDEST copy and lacks
the ``include_entry_points`` seam — do not use it as the template; its
tests can only assert set-membership because of that omission.

The determinism guarantee
-------------------------
``include_entry_points=False`` aggregates ONLY ``extra_providers``, so a
test may assert an EXACT list rather than a membership. With the flag left
``True`` the result depends on which packages happen to be installed in the
running environment, and an exact-list assertion would pass on the author's
machine and fail in CI — or, worse, the reverse.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Callable

from ._errors import StoreError
from ._policy import Schema, WriterPolicy
from ._target import StoreTarget

__all__ = [
    "ENTRY_POINT_GROUP",
    "StorePlugin",
    "StorePluginProvider",
    "discover_store_plugins",
    "plugin_for",
    "resolve_target",
]

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


@dataclass(frozen=True)
class StorePlugin:
    """One leaf's declaration of a store it owns the semantics of.

    Fields
    ------
    name
        The store's schema name, and the dedup key. Becomes the table-name
        prefix, so it must be an identifier.
    pkg
        The package short name (``"cards"``, ``"sac"``). Decides where the
        store resolves — see :func:`resolve_target`. NOT a free label: two
        plugins naming different ``pkg`` values resolve to different stores.
    schema
        The leaf's field policies. This is the payload that matters: every
        field states its merge rule explicitly, because there is no default
        and a wrong one loses data without raising.
    writer_policy
        Whether the store enforces one writer per record. ``MULTI_WRITER``
        for anything whose owner field is legitimately changed by
        non-owners — a card store, where reassignment and operator resolves
        are routine.
    provider
        The declaring pip package (``"scitex-cards"``). Carried so a
        federation listing can say who is responsible for a declaration,
        and so a duplicate-name collision names both claimants.
    description
        Short human-readable purpose, shown in listings.
    """

    name: str
    pkg: str
    schema: Schema
    writer_policy: WriterPolicy
    provider: str
    description: str = ""

    def __post_init__(self) -> None:
        # Validate at CONSTRUCTION so a malformed declaration never reaches
        # the aggregator, and so the traceback points at the leaf that wrote
        # it rather than at whoever happened to call discovery.
        if not isinstance(self.name, str) or not self.name.isidentifier():
            raise ValueError(
                f"StorePlugin.name must be a valid identifier (it prefixes "
                f"the store's table names); got {self.name!r}"
            )
        if not isinstance(self.pkg, str) or not self.pkg.strip():
            raise ValueError(
                f"StorePlugin({self.name!r}).pkg must name the owning "
                f"package short name; got {self.pkg!r}. It decides which "
                "store this resolves to, so an empty value would silently "
                "point at nothing."
            )
        if not isinstance(self.schema, Schema):
            raise ValueError(
                f"StorePlugin({self.name!r}).schema must be a "
                f"scitex_dev.store.Schema, got {type(self.schema).__name__}. "
                "Build it with Schema.build(), which is what checks that "
                "every field states a merge rule."
            )
        if self.schema.name != self.name:
            raise ValueError(
                f"StorePlugin({self.name!r}) carries schema "
                f"{self.schema.name!r}. They must agree: the schema name is "
                "the table prefix and the plugin name is how the federation "
                "refers to it, so a mismatch would have discovery and the "
                "database disagree about which store is which."
            )
        if not isinstance(self.writer_policy, WriterPolicy):
            raise ValueError(
                f"StorePlugin({self.name!r}).writer_policy must be a "
                f"WriterPolicy, got {self.writer_policy!r}. Legal values: "
                f"{[p.value for p in WriterPolicy]}."
            )
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError(
                f"StorePlugin({self.name!r}).provider must name the "
                f"declaring package; got {self.provider!r}"
            )

    def describe(self) -> str:
        """One line for a federation listing."""
        text = (
            f"{self.name:16} pkg={self.pkg:10} "
            f"{self.writer_policy.value:14} "
            f"{len(self.schema.fields)} field(s)  [{self.provider}]"
        )
        return f"{text}  {self.description}" if self.description else text


#: Provider callable shape leaves register under the entry-point group.
StorePluginProvider = Callable[[], "list[StorePlugin]"]


def _iter_entry_points(group: str):
    """Yield entry points for ``group``, compatible with Python 3.9+."""
    from importlib.metadata import entry_points

    if sys.version_info >= (3, 10):
        return entry_points(group=group)
    eps = entry_points()
    return eps.get(group, [])


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
) -> "list[StorePlugin]":
    """Every store declaration installed in this environment.

    ``include_entry_points=False`` is the unit-test isolation seam: it
    aggregates ONLY ``extra_providers``, so exact-list assertions stay valid
    regardless of which real leaves are installed in the running env.

    Dedup is by ``name``, FIRST WINS in provider order (entry points, then
    ``extra_providers``). The returned list is sorted by name so two runs
    over the same environment produce the same order.

    A provider that raises is SKIPPED with a warning rather than taking the
    federation down. One leaf shipping a broken declaration must not stop
    every other leaf's store from resolving — but it must not pass
    unnoticed either, hence the warning with a traceback.
    """
    providers: "list[StorePluginProvider]" = []
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
) -> StorePlugin:
    """The plugin declaring store ``name``, or a pointed error.

    Raises :class:`~._errors.StoreError` naming every store the federation
    DID find. An empty federation is called out separately: "no leaf has
    declared a store" and "that particular store is not declared" have
    different causes — a missing install versus a typo — and one message
    covering both sends the reader looking in the wrong place.
    """
    found = discover_store_plugins(
        extra_providers=extra_providers,
        include_entry_points=include_entry_points,
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


def resolve_target(plugin: StorePlugin) -> StoreTarget:
    """WHERE ``plugin``'s store lives on this host.

    Centralised on purpose, and this is the load-bearing sentence of the
    module: **a leaf does not resolve its own store target.**

    Per-consumer resolution is what produced the 2026-08-11 split. Two
    processes on ``scitex-compute-04`` each resolved the card store their
    own way — one to the host's Postgres on ``:55432``, one through an SSH
    tunnel presented as ``127.0.0.1:5442`` to the NAS's — and both were
    "correct" by their own configuration. 404 cards ended up on one and 146
    on the other, and every read, write and ack on both reported success.

    Resolution therefore goes through :func:`~._host.host_store`, which has
    exactly two steps (``SCITEX_STORE_DSN`` or the per-host Postgres) and
    deliberately NO SQLite fallback: a host whose Postgres is down must
    fail loudly rather than start writing to a private local file that
    shares nothing.
    """
    from ._host import host_store

    return host_store(pkg=plugin.pkg, name=plugin.name)

# EOF
