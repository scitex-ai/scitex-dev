#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/hooks/_discover.py
"""Aggregate every package's declared agent guardrails into one corpus.

The same entry-point federation used by ``scitex_dev.jobs`` /
``scitex_dev.system_deps`` / ``scitex_dev.gate`` / ``scitex_dev.host_config``.
Leaves DECLARE; scitex-dev DISCOVERS.

SCITEX-DEV IS A LEAF HERE, NOT A PARENT
---------------------------------------
This module contains NO built-in provider and NO special case for scitex-dev.
scitex-dev declares its own rules by registering ``scitex_dev._hook_rules:provide``
under the very same entry-point group every other package uses, so its rules
dedup against everyone else's on identical terms and the aggregator is not a
special case of itself.

That is a deliberate departure from ``discover_jobs`` and
``discover_gate_checks``, which both PREPEND a hardcoded ``_builtin_*``
provider before the entry points. ``discover_system_deps`` is the leaf-clean
precedent and the one copied here, per the operator's requirement that
scitex-dev appear "as a leaf among the others, not as a privileged parent"
(2026-08-11: 「ここは自己再帰的にならないように、scitex-dev を leaf package として
扱って」).

The known cost of leaf-cleanliness, accepted with eyes open: entry-point
metadata lives in the INSTALLED dist-info, so an editable checkout whose
``pyproject.toml`` has moved on but which has not been reinstalled advertises
the OLD set. ``discover_system_deps`` accepted the same trade, and a stale
declaration is a far better failure than an aggregator that cannot be
reasoned about.

DETERMINISM GUARANTEE
---------------------
Rules are deduped by ``id`` and returned sorted by ``id``, so the resulting
SET is stable regardless of entry-point iteration order. Only the metadata of
a DUPLICATED id is order-dependent (first provider wins), and that case is
warned about rather than silently resolved.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import replace
from typing import Callable

from ._spec import HookRule

_logger = logging.getLogger(__name__)

#: Entry-point group every leaf registers its hook-rule provider under.
ENTRY_POINT_GROUP = "scitex_dev.hooks"


def _iter_entry_points(group: str):
    """Yield entry points for ``group``, compatible with Python 3.9+."""
    from importlib.metadata import entry_points

    if sys.version_info >= (3, 10):
        return entry_points(group=group)
    return entry_points().get(group, [])


def _anchor_of(ep) -> str:
    """The top-level module an entry point's rules resolve their assets against.

    ``ep.value`` is ``"pkg.sub._hook_rules:provide"``; the anchor is ``pkg``.
    Taking the TOP-LEVEL package (not the declaring submodule) is deliberate:
    a leaf ships its hook assets under its package root, and anchoring at the
    submodule would make every declaration carry ``../..`` segments.
    """
    module = getattr(ep, "module", None)
    if not module:
        value = getattr(ep, "value", "") or ""
        module = value.split(":", 1)[0]
    return module.split(".", 1)[0] if module else ""


def _dist_of(ep) -> str:
    """Return the DISTRIBUTION name behind ``ep`` (``scitex-agent-container``).

    The sibling of :func:`_anchor_of`, and deliberately a different string:
    that one yields an importable MODULE (``scitex_agent_container``), this
    one yields the packaging identity. ``resolve_asset`` needs the module;
    ownership and dedup need the distribution. Conflating them is the bug
    this stamping exists to make unreachable.

    ``ep.dist`` is absent on entry points built by hand (tests, in-process
    registration), so an empty string is a legitimate answer here and the
    caller must leave the declared value alone rather than blank it.
    """
    dist = getattr(ep, "dist", None)
    return getattr(dist, "name", "") or ""


def _make_ep_provider(ep) -> Callable[[], list[HookRule]]:
    """Wrap an entry point into a provider callable returning HookRules.

    Rules come back with ``owner_module`` AND ``provider`` stamped from the
    entry point when the leaf left them empty, so a package never has to
    repeat its own identity and cannot get it wrong.

    Stamping only fills a BLANK. An explicitly declared value always wins —
    a leaf that ships rules on behalf of another distribution (a shim, a
    vendored ruleset) must be able to say so, and discovery cannot tell that
    case apart from a mistake.
    """

    def _provider() -> list[HookRule]:
        get_rules = ep.load()
        anchor = _anchor_of(ep)
        dist = _dist_of(ep)
        stamped = []
        for rule in get_rules():
            if isinstance(rule, HookRule):
                if not rule.owner_module and anchor:
                    rule = replace(rule, owner_module=anchor)
                if not rule.provider and dist:
                    rule = replace(rule, provider=dist)
            stamped.append(rule)
        return stamped

    _provider.__name__ = f"entry_point:{getattr(ep, 'name', '?')}"
    return _provider


def discover_hooks(
    *,
    event: str | None = None,
    extra_providers: list[Callable[[], list[HookRule]]] | None = None,
    include_entry_points: bool = True,
) -> list[HookRule]:
    """Return every declared hook rule, deduped by ``id`` and sorted by ``id``.

    Parameters
    ----------
    event
        Optional filter -- return only rules attaching to this lifecycle
        point. Applied BEFORE the dedup check, so a filtered-out duplicate
        does not consume the id slot.
    extra_providers
        Additional provider callables, appended after the discovered ones.
        The unit-test injection seam.
    include_entry_points
        ``False`` aggregates ONLY ``extra_providers`` -- the unit-test
        isolation seam that keeps exact-list assertions valid regardless of
        which real providers happen to be installed in the running
        environment. scitex-dev's own rules arrive through an entry point
        like every other package's, so this drops them too; that symmetry is
        the point.
    """
    providers: list[Callable[[], list[HookRule]]] = []
    if include_entry_points:
        for ep in _iter_entry_points(ENTRY_POINT_GROUP):
            providers.append(_make_ep_provider(ep))
    if extra_providers:
        providers.extend(extra_providers)

    by_id: dict[str, HookRule] = {}
    by_script: dict[str, str] = {}
    for provider in providers:
        try:
            rules = provider()
        except Exception:
            # A broken leaf must not take the whole corpus down: a package
            # that fails to import would otherwise disarm every OTHER
            # package's guardrails too.
            _logger.warning(
                "Failed to load hook rules from provider %r", provider, exc_info=True
            )
            continue
        for rule in rules:
            if not isinstance(rule, HookRule):
                _logger.warning(
                    "Provider %r yielded a non-HookRule %r; skipping",
                    provider,
                    rule,
                )
                continue
            if event is not None and rule.event != event:
                continue
            if rule.id in by_id:
                _logger.warning(
                    "Duplicate hook rule %r ignored (first provider wins)",
                    rule.id,
                )
                continue
            if rule.script is not None and rule.script in by_script:
                _logger.warning(
                    "Hook rule %r binds script %s, already claimed by %r -- "
                    "two rules sharing one script cannot be skipped or "
                    "retired independently; ignoring the second "
                    "(first provider wins)",
                    rule.id,
                    rule.script,
                    by_script[rule.script],
                )
                continue
            by_id[rule.id] = rule
            if rule.script is not None:
                by_script[rule.script] = rule.id

    return [by_id[rid] for rid in sorted(by_id)]


def rules_of_provider(provider: str, **kwargs) -> list[HookRule]:
    """Return discovered rules declared by ``provider``."""
    return [r for r in discover_hooks(**kwargs) if r.provider == provider]


__all__ = ["ENTRY_POINT_GROUP", "discover_hooks", "rules_of_provider"]
