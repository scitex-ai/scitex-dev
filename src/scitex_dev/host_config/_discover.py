#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/host_config/_discover.py
"""Aggregating every HostConfigSpec declared across the ecosystem."""

from __future__ import annotations

import logging
import os
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_logger = logging.getLogger(__name__)

from ._spec import HostConfigSpec

def _iter_entry_points(group: str):
    """Yield entry points for ``group``, compatible with Python 3.9+."""
    from importlib.metadata import entry_points

    if sys.version_info >= (3, 10):
        return entry_points(group=group)
    eps = entry_points()
    return eps.get(group, [])


def _make_ep_provider(ep) -> Callable[[], list[HostConfigSpec]]:
    """Wrap an entry point into a provider returning HostConfigSpecs."""

    def _provider() -> list[HostConfigSpec]:
        get_specs = ep.load()
        return list(get_specs())

    _provider.__name__ = f"entry_point:{getattr(ep, 'name', '?')}"
    return _provider


def _builtin_host_config() -> list[HostConfigSpec]:
    """scitex-dev's OWN declarations, merged through an INTERNAL provider.

    Deliberately NOT an entry point, mirroring ``discover_jobs``'s
    ``_builtin_jobs``: entry-point metadata lives in the INSTALLED
    dist-info, so an editable checkout whose ``pyproject.toml`` has moved
    on but which has not been reinstalled advertises the OLD set. For a
    scheduled job that is an annoyance; for the declaration that keeps a
    host's forensic logging alive it is a silent, host-specific
    disappearance -- the exact failure mode this federation exists to
    prevent. An internal provider is always present, on every host, the
    moment the code is.

    The ``scitex_dev.host_config`` entry-point group is therefore
    reserved for DOWNSTREAM packages.
    """
    from ._declarations import provide

    return provide()


def _conflicting_claim(
    spec: HostConfigSpec, existing
) -> HostConfigSpec | None:
    """Return the already-accepted spec that FIGHTS ``spec``, if any.

    Two declarations of the same ``path`` only conflict when they can
    both land on the SAME host. Per-host declarations that share a path
    but name disjoint ``hosts`` are the opposite of a conflict -- they
    are how a fleet expresses "this file, different content per
    machine" (a requested DHCP address, a hostname, a per-host mount).

    The earlier version of this check keyed on ``path`` alone and so
    dropped every per-host declaration after the first, keeping only the
    alphabetically-first host's copy and logging a warning nothing
    surfaces. Nine declarations in, one survivor, no error: exactly the
    silent loss this federation exists to prevent, committed by the
    guard meant to prevent it.

    An empty ``hosts`` means "every host", so it overlaps with
    everything -- including another empty one.
    """
    for other in existing:
        if not spec.hosts or not other.hosts:
            return other
        if set(spec.hosts) & set(other.hosts):
            return other
    return None


def discover_host_config(
    *,
    extra_providers: list[Callable[[], list[HostConfigSpec]]] | None = None,
    include_entry_points: bool = True,
) -> list[HostConfigSpec]:
    """Aggregate every ``HostConfigSpec`` declared across the ecosystem.

    Sources, in order: scitex-dev's built-ins
    (``_builtin_host_config``), then every ``scitex_dev.host_config``
    entry point, then ``extra_providers``.

    Same contract as ``discover_jobs`` / ``discover_system_deps``: walk
    the entry-point group, tolerate a provider that raises (logged
    warning, skipped, so one broken leaf never wedges the aggregation),
    de-duplicate FIRST-WINS, and return sorted output for determinism.

    De-duplication is keyed by ``name``. A second declaration of the
    same ``path`` under a DIFFERENT name is also reported -- that is the
    genuinely dangerous collision (two packages fighting over one file,
    each undoing the other every time its job runs), and silently
    letting both through would produce exactly the invisible flapping
    this federation exists to prevent.

    ``include_entry_points=False`` is the unit-test isolation seam,
    mirroring ``discover_system_deps``: it aggregates ONLY
    ``extra_providers`` -- built-ins included -- so exact-list
    assertions stay valid regardless of what is installed in the
    running env.
    """
    providers: list[Callable[[], list[HostConfigSpec]]] = []
    if include_entry_points:
        providers.append(_builtin_host_config)
        for ep in _iter_entry_points(ENTRY_POINT_GROUP):
            providers.append(_make_ep_provider(ep))
    if extra_providers:
        providers.extend(extra_providers)

    by_name: dict[str, HostConfigSpec] = {}
    by_path: dict[str, list[HostConfigSpec]] = {}
    for provider in providers:
        try:
            specs = provider()
        except Exception:
            _logger.warning(
                "Failed to load host config from provider %r",
                provider,
                exc_info=True,
            )
            continue
        for spec in specs:
            if not isinstance(spec, HostConfigSpec):
                _logger.warning(
                    "Provider %r yielded a non-HostConfigSpec %r; skipping",
                    provider,
                    spec,
                )
                continue
            if spec.name in by_name:
                _logger.warning(
                    "Duplicate host config %r ignored (first provider wins)",
                    spec.name,
                )
                continue
            rival = _conflicting_claim(spec, by_path.get(spec.path, ()))
            if rival is not None:
                _logger.warning(
                    "Host config %r targets %s on a host %r also claims -- "
                    "two declarations for one file on one host will fight; "
                    "ignoring the second (first provider wins)",
                    spec.name,
                    spec.path,
                    rival.name,
                )
                continue
            by_name[spec.name] = spec
            by_path.setdefault(spec.path, []).append(spec)

    return [by_name[name] for name in sorted(by_name)]


