#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/versioning/_config.py

"""The one object a leaf instantiates. Everything sac hardcoded lives here.

sac's ``_freshness`` baked in its distribution name, PyPI URL, release
workflow file, systemd unit, ``SAC_FRESHNESS_*`` env prefix and cache
subpath. None of that is generic. A reusable primitive cannot: scitex-io,
figrecipe and scitex-dev each ship under a different name, publish through a
different workflow, run (or do not run) a different daemon, and must not
collide on the same env vars or cache file.

So all of it is parameterised into :class:`VersioningConfig`. A leaf builds
one and hands it to :func:`scitex_dev.versioning.check_currency`; the
primitive supplies every honest default it can derive from the ``dist``
name, and the leaf overrides only what is special about it.

WHAT STAYS IN THE LEAF (not here): the actual ``sac freshness`` verbs, the
CLI-entrypoint hook, the cron deployer, and — crucially — the CONTENTS of
the symbol-expectation registry. A symbol expectation names a fix in the
leaf's own code; only the leaf knows it. This config carries the
*expectations tuple* as a seam, defaulting empty, so the primitive never
invents claims about code it cannot see.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ._symbols import SymbolExpectation

__all__ = ["VersioningConfig"]


def _default_prefix(dist: str) -> str:
    """``scitex-agent-container`` -> ``SCITEX_AGENT_CONTAINER_FRESHNESS``.

    The env-var namespace every knob hangs off. Deriving it from the dist
    name is what stops two leaves in the same shell from fighting over one
    ``FRESHNESS_QUIET``.
    """
    stem = dist.strip().upper().replace("-", "_").replace(".", "_")
    return f"{stem}_FRESHNESS"


@dataclass(frozen=True)
class VersioningConfig:
    """Everything a single leaf needs to answer "is my code current?".

    Only ``dist`` is required. Every other field either has a safe generic
    default or is honestly derived from ``dist`` at construction (see
    :meth:`__post_init__`), so the minimal call is::

        VersioningConfig(dist="scitex-io")

    Attributes:
        dist: The PyPI/distribution name, e.g. ``"scitex-dev"``.
        module: Import name. Defaults to ``dist`` with ``-``/``.`` -> ``_``.
        pypi_json_url: The PyPI JSON endpoint. Defaults to the standard
            ``https://pypi.org/pypi/<dist>/json``.
        release_workflow: The GitHub Actions workflow file that publishes
            releases, e.g. ``"pypi.yml"``. ``None`` disables the
            release-run check (that leaf simply does not get it).
        systemd_unit: The ``--user`` unit of a long-lived daemon whose
            running-vs-installed lag matters, e.g. ``"sac-listen.service"``.
            ``None`` disables the running-vs-installed check.
        env_prefix: Namespace for the env knobs (``<PREFIX>_CACHE``,
            ``<PREFIX>_TTL_S``, ``<PREFIX>_QUIET``, ``<PREFIX>_SEVERITY``,
            ``<PREFIX>_DEBUG``). Derived from ``dist`` when unset.
        cache_subpath: Path fragments UNDER ``$SCITEX_DIR`` for this leaf's
            cache file. Kept relative so it is never joined to a home dir at
            import time. Derived from ``dist`` when unset.
        expectations: Symbol expectations proving named fixes are in the
            LOADED code. Supplied by the leaf; empty here on purpose.
        repo_root: An explicit checkout path for the git/tag checks. ``None``
            lets :class:`LiveSources` discover it from the module origin.
    """

    dist: str
    module: str | None = None
    pypi_json_url: str | None = None
    release_workflow: str | None = None
    systemd_unit: str | None = None
    env_prefix: str | None = None
    cache_subpath: tuple[str, ...] = ()
    expectations: tuple[SymbolExpectation, ...] = field(default_factory=tuple)
    repo_root: Path | None = None

    def __post_init__(self) -> None:
        # frozen dataclass: fill derived defaults via object.__setattr__.
        object.__setattr__(self, "dist", self.dist.strip())
        if not self.dist:
            raise ValueError("VersioningConfig.dist must be a non-empty name")
        if self.module is None:
            object.__setattr__(
                self, "module", self.dist.replace("-", "_").replace(".", "_")
            )
        if self.pypi_json_url is None:
            object.__setattr__(
                self, "pypi_json_url", f"https://pypi.org/pypi/{self.dist}/json"
            )
        if not self.env_prefix:
            object.__setattr__(self, "env_prefix", _default_prefix(self.dist))
        if not self.cache_subpath:
            object.__setattr__(
                self,
                "cache_subpath",
                (self.module, "runtime", "version-currency.json"),
            )

    # -- derived env-var names ------------------------------------------
    # Resolved from the prefix so a leaf never has to spell these out and
    # two leaves can never collide on one namespace.
    @property
    def env_cache(self) -> str:
        return f"{self.env_prefix}_CACHE"

    @property
    def env_ttl(self) -> str:
        return f"{self.env_prefix}_TTL_S"

    @property
    def env_quiet(self) -> str:
        return f"{self.env_prefix}_QUIET"

    @property
    def env_severity(self) -> str:
        return f"{self.env_prefix}_SEVERITY"

    @property
    def env_debug(self) -> str:
        return f"{self.env_prefix}_DEBUG"


# EOF
