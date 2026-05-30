#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical federated scheduled-job contract for the SciTeX ecosystem.

This module defines the single ``JobSpec`` dataclass that *every*
ecosystem package imports, and the ``discover_jobs()`` aggregator that
collects jobs from all packages via the ``scitex_dev.jobs`` entry-point
group.

The discovery mechanism mirrors the linter-plugin federation pattern
(see ``scitex_dev.linter._plugin_loader``): each provider registers an
entry point in the ``scitex_dev.jobs`` group that loads to a *callable*
returning ``list[JobSpec]``. A failing or absent provider is tolerated
with a logged warning so one broken package never wedges the whole
aggregation.

Contract for downstream packages
--------------------------------
1. ``pip``-install ``scitex-dev`` (for the ``JobSpec`` import only — no
   heavy runtime dependency).
2. Define a module-level callable returning ``list[JobSpec]``::

       from scitex_dev.jobs import JobSpec

       def provide_jobs() -> list[JobSpec]:
           return [
               JobSpec(
                   name="sac.accounts-refresh",
                   schedule="0 */4 * * *",
                   command="sac accounts refresh --all",
                   description="Rotate stored OAuth access tokens.",
                   kind="systemd",
                   on_boot_sec="15min",
                   on_unit_active_sec="4h",
                   timeout_sec=120,
               ),
           ]

3. Register it in ``pyproject.toml``::

       [project.entry-points."scitex_dev.jobs"]
       my-package = "my_package._jobs_plugin:provide_jobs"

``scitex-dev ecosystem cron|systemd|daemon`` then surface the job
automatically.

Naming
------
``JobSpec.name`` is the package-prefixed unique id, e.g.
``"sac.accounts-refresh"``. The prefix keeps names globally unique and
makes the owning package obvious in ``list`` output. scitex-dev's own
built-in jobs keep their historical bare slugs (``ci-watch``,
``quota-keepalive``) for backward compatibility with the existing
``scitex-dev cron`` CLI.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Callable

_logger = logging.getLogger(__name__)

#: Entry-point group downstream packages register their job providers in.
ENTRY_POINT_GROUP = "scitex_dev.jobs"


@dataclass(frozen=True)
class JobSpec:
    """One scheduled job, shared across the SciTeX ecosystem.

    Fields
    ------
    name
        Package-prefixed unique id, e.g. ``"sac.accounts-refresh"``.
    schedule
        Cron expression, e.g. ``"0 */2 * * *"``. Used directly for
        ``kind == "cron"`` and as a fallback to derive a systemd timer
        cadence when ``on_unit_active_sec`` is not given.
    command
        Shell command to execute.
    description
        Human-readable summary shown in ``list`` output.
    kind
        ``"cron"`` | ``"systemd"`` | ``"daemon"``. Selects which
        installer surfaces the job.
    on_boot_sec
        systemd timer ``OnBootSec`` (e.g. ``"15min"``). systemd only.
    on_unit_active_sec
        systemd timer ``OnUnitActiveSec`` (e.g. ``"2h"``). systemd only.
    timeout_sec
        Hard timeout in seconds; maps to systemd ``TimeoutStartSec``.
    """

    name: str
    schedule: str
    command: str
    description: str
    kind: str = "cron"
    on_boot_sec: str | None = None
    on_unit_active_sec: str | None = None
    timeout_sec: int | None = None


def _iter_entry_points(group: str):
    """Yield entry points for ``group``, compatible with Python 3.9+."""
    from importlib.metadata import entry_points

    if sys.version_info >= (3, 10):
        return entry_points(group=group)
    eps = entry_points()
    return eps.get(group, [])


def _builtin_jobs() -> list[JobSpec]:
    """scitex-dev's own jobs, adapted from the legacy ``JOB_REGISTRY``.

    Registered through the same provider path as external packages so
    there is a single code path. The legacy ``cron`` CLI keeps its own
    ``JOB_REGISTRY`` for backward compatibility; this adapts those
    entries into the canonical ``JobSpec`` form (``kind="cron"``).
    """
    from scitex_dev._cli.cron._jobs import JOB_REGISTRY

    return [
        JobSpec(
            name=spec.name,
            schedule=spec.schedule,
            command=spec.command,
            description=spec.description,
            kind="cron",
        )
        for spec in JOB_REGISTRY.values()
    ]


def discover_jobs(
    *,
    extra_providers: list[Callable[[], list[JobSpec]]] | None = None,
) -> list[JobSpec]:
    """Aggregate every ``JobSpec`` across the ecosystem.

    Sources, in order:

    1. scitex-dev's built-in jobs (``_builtin_jobs``).
    2. Every callable registered under the ``scitex_dev.jobs``
       entry-point group.
    3. ``extra_providers`` — an injection seam for tests (mirrors the
       ``read_fn`` / ``write_fn`` seams in the cron crontab helpers) so
       a mock provider can be supplied without touching installed
       entry-points.

    A provider that raises (or whose entry point fails to load) is
    skipped with a logged warning — exactly like the linter plugin
    loader — so one broken package never wedges the aggregation.

    De-duplication: jobs are keyed by ``name``. On collision the
    *first* provider wins (built-ins are first, then entry-points in
    discovery order); the duplicate is dropped with a logged warning.
    This matches the linter loader's "later registration is ignored on
    id collision" behavior (provider-wins / first-wins).
    """
    providers: list[Callable[[], list[JobSpec]]] = [_builtin_jobs]

    for ep in _iter_entry_points(ENTRY_POINT_GROUP):
        providers.append(_make_ep_provider(ep))

    if extra_providers:
        providers.extend(extra_providers)

    by_name: dict[str, JobSpec] = {}
    for provider in providers:
        try:
            jobs = provider()
        except Exception:
            _logger.warning(
                "Failed to load jobs from provider %r", provider, exc_info=True
            )
            continue
        for job in jobs:
            if not isinstance(job, JobSpec):
                _logger.warning(
                    "Provider %r yielded a non-JobSpec object %r; skipping",
                    provider,
                    job,
                )
                continue
            if job.name in by_name:
                _logger.warning(
                    "Duplicate job name %r ignored (first provider wins)",
                    job.name,
                )
                continue
            by_name[job.name] = job

    return [by_name[name] for name in sorted(by_name)]


def _make_ep_provider(ep) -> Callable[[], list[JobSpec]]:
    """Wrap an entry point into a provider callable returning JobSpecs."""

    def _provider() -> list[JobSpec]:
        get_jobs = ep.load()
        result = get_jobs()
        return list(result)

    _provider.__name__ = f"entry_point:{getattr(ep, 'name', '?')}"
    return _provider


def jobs_of_kind(kind: str, **kwargs) -> list[JobSpec]:
    """Return discovered jobs whose ``kind`` matches ``kind``."""
    return [j for j in discover_jobs(**kwargs) if j.kind == kind]


__all__ = [
    "JobSpec",
    "ENTRY_POINT_GROUP",
    "discover_jobs",
    "jobs_of_kind",
]


# EOF
