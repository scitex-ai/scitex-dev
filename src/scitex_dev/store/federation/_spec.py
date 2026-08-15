#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/store/federation/_spec.py
"""The contract a leaf declares: :class:`StorePlugin`.

The division of labour, and why it is this way round
----------------------------------------------------
A leaf package knows things scitex-dev cannot: that a card's ``status`` is
last-writer-wins but its ``created_at`` is immutable, that ``comments`` is
an append-only collection and ``last_activity`` must never move backwards.
Those are DOMAIN facts. Nobody outside scitex-cards can state them, and a
default guessed here would be wrong silently — see :mod:`.._policy` for why
that is the one thing this primitive refuses to do.

Everything else is machinery: the oplog, the clock, the cursors, the gap
assertion, and — critically — WHERE THE STORE IS. A leaf declares a
:class:`StorePlugin`; it does not resolve its own target. See
:mod:`._resolve` for why that half is centralised.

This module is DATA ONLY. It defines the shape and validates it; it
discovers nothing and opens nothing. Kept separate from :mod:`._discover`
for the reason ``scitex_dev.gate._spec`` is separate from
``gate._discover``: a leaf importing the contract must not drag in the
entry-point machinery that reads the whole environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .._policy import Schema, WriterPolicy

__all__ = ["StorePlugin", "StorePluginProvider"]


@dataclass(frozen=True)
class StorePlugin:
    """One leaf's declaration of a store it owns the semantics of.

    Fields
    ------
    name
        The store's schema name, and the dedup key. Becomes the table-name
        prefix, so it must be an identifier.
    pkg
        The package short name (``"cards"``, ``"sac"``, ``"dev"``). Decides
        where the store resolves — see :func:`.._resolve.resolve_target`.
        NOT a free label: two plugins naming different ``pkg`` values
        resolve to different stores.
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

# EOF
