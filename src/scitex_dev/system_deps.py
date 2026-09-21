#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/system_deps.py
"""Federated SYSTEM dependency declaration for the SciTeX ecosystem.

Every scitex leaf declares the system software it needs by registering a
callable under the ``scitex_dev.system_deps`` entry-point group;
``discover_system_deps()`` aggregates them. This replaces hardcoding
install lists in container definitions -- the same entry-point federation
used by ``scitex_dev.jobs`` / ``discover_jobs``.

Two install kinds share the one group:

* ``kind="apt"`` (the original): a distro package installed with root at
  IMAGE-BUILD time (container ``%post`` / Dockerfile), NEVER at agent
  boot (agents are rootless ``--userns`` and cannot apt-install).
  ``scitex-dev ecosystem system-deps list`` emits exactly these names,
  so ``apt-get install $(... list)`` keeps working.
* ``kind="script"``: a user-space ``curl | bash`` installer (no root;
  runs at HOST-CONFIGURE time, e.g. the Hermes agent installer). The
  declaration pins the URL plus the non-interactive args and a verify
  command, so a host install is a reviewed string, not a pasted one-liner.

Example provider (in a leaf package)::

    # scitex_writer/_system_deps.py  (apt kind)
    from scitex_dev.system_deps import SystemDepSpec

    def provide() -> list[SystemDepSpec]:
        return [
            SystemDepSpec("texlive-latex-extra", "LaTeX compile", "scitex-writer"),
            SystemDepSpec("biber", "bibliography backend", "scitex-writer"),
        ]

    # scitex_agent_container/_system_deps.py  (script kind)
    def provide() -> list[SystemDepSpec]:
        return [
            SystemDepSpec(
                "hermes-agent",
                "sac's Hermes harness runs resident on every fleet host",
                "scitex-agent-container",
                kind="script",
                install_url="https://hermes-agent.nousresearch.com/install.sh",
                install_args=("--skip-setup", "--non-interactive"),
                verify_command="hermes --version",
            ),
        ]

    # pyproject.toml
    # [project.entry-points."scitex_dev.system_deps"]
    # scitex-writer = "scitex_writer._system_deps:provide"
"""

from __future__ import annotations

import scitex_logging as slogging
import sys
from dataclasses import dataclass
from typing import Callable

_logger = slogging.getLogger(__name__)

#: Entry-point group every leaf registers its system-dep provider under.
ENTRY_POINT_GROUP = "scitex_dev.system_deps"

#: Accepted ``SystemDepSpec.kind`` values: ``"apt"`` (root, image-build
#: time) or ``"script"`` (user-space ``curl | bash`` installer,
#: host-configure time).
INSTALL_KINDS = ("apt", "script")


@dataclass(frozen=True)
class SystemDepSpec:
    """One system dependency a scitex package needs.

    Fields
    ------
    package
        Identity of the dependency: the apt package name for
        ``kind="apt"`` (e.g. ``"ffmpeg"``), the installed tool's name for
        ``kind="script"`` (e.g. ``"hermes-agent"``). The aggregation
        dedup key.
    purpose
        Short human-readable reason -- shown in listings and docs.
    provider
        The declaring package (e.g. ``"scitex-writer"``).
    apt_repo
        ``kind="apt"`` only: optional extra apt source needed before
        install -- an ``add-apt-repository`` argument such as
        ``"ppa:apptainer/ppa"``. ``None`` when the package is in the
        default repos.
    kind
        ``"apt"`` or ``"script"`` (see ``INSTALL_KINDS``).
    install_url
        ``kind="script"`` only, required: the pinned installer URL.
        Plain http is refused -- a fleet-wide install must not be
        downgradeable on the wire.
    install_args
        ``kind="script"`` only: extra argv passed after the installer
        (``bash -s -- ...``). Must keep the install non-interactive --
        a fleet install that stops to ask is not an install.
    verify_command
        Command proving the install took (e.g. ``"hermes --version"``).
        Observation is the only accepted proof: an installer that
        "succeeded" without a verifiable artifact is not done.
    """

    package: str
    purpose: str
    provider: str
    apt_repo: str | None = None
    kind: str = "apt"
    install_url: str | None = None
    install_args: tuple[str, ...] = ()
    verify_command: str | None = None

    def __post_init__(self) -> None:
        # Fail EARLY at construction so a malformed declaration never reaches
        # the aggregator or a container build.
        if not isinstance(self.package, str) or not self.package.strip():
            raise ValueError(
                f"SystemDepSpec.package must be a non-empty name; "
                f"got {self.package!r}"
            )
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError(
                f"SystemDepSpec({self.package!r}).provider must name the "
                f"declaring package; got {self.provider!r}"
            )
        if self.kind not in INSTALL_KINDS:
            raise ValueError(
                f"SystemDepSpec({self.package!r}).kind must be one of "
                f"{INSTALL_KINDS}; got {self.kind!r}"
            )
        if self.kind == "apt":
            if self.install_url is not None:
                raise ValueError(
                    f"SystemDepSpec({self.package!r}): kind='apt' must not "
                    f"carry install_url; declare kind='script' instead"
                )
            if self.install_args:
                raise ValueError(
                    f"SystemDepSpec({self.package!r}): kind='apt' must not "
                    f"carry install_args; declare kind='script' instead"
                )
        else:  # kind == "script"
            if self.apt_repo is not None:
                raise ValueError(
                    f"SystemDepSpec({self.package!r}): kind='script' must "
                    f"not carry apt_repo (no apt involved)"
                )
            if (
                not isinstance(self.install_url, str)
                or not self.install_url.startswith("https://")
            ):
                raise ValueError(
                    f"SystemDepSpec({self.package!r}): kind='script' "
                    f"requires a pinned https:// install_url; "
                    f"got {self.install_url!r}"
                )
            for arg in self.install_args:
                if not isinstance(arg, str) or not arg.strip():
                    raise ValueError(
                        f"SystemDepSpec({self.package!r}): install_args "
                        f"must be non-empty strings; got {arg!r}"
                    )
        if self.verify_command is not None and not self.verify_command.strip():
            raise ValueError(
                f"SystemDepSpec({self.package!r}): verify_command must be "
                f"a non-empty command when given"
            )


def _iter_entry_points(group: str):
    """Yield entry points for ``group``, compatible with Python 3.9+."""
    from importlib.metadata import entry_points

    if sys.version_info >= (3, 10):
        return entry_points(group=group)
    eps = entry_points()
    return eps.get(group, [])


def _make_ep_provider(ep) -> Callable[[], list[SystemDepSpec]]:
    """Wrap an entry point into a provider callable returning SystemDepSpecs."""

    def _provider() -> list[SystemDepSpec]:
        get_deps = ep.load()
        return list(get_deps())

    _provider.__name__ = f"entry_point:{getattr(ep, 'name', '?')}"
    return _provider


def discover_system_deps(
    *,
    extra_providers: list[Callable[[], list[SystemDepSpec]]] | None = None,
    include_entry_points: bool = True,
) -> list[SystemDepSpec]:
    """Aggregate every ``SystemDepSpec`` declared across the ecosystem.

    Walks the ``scitex_dev.system_deps`` entry-point group (every leaf that
    registers a provider) plus any ``extra_providers`` -- a test-injection seam
    that mirrors ``discover_jobs``'s, so a fake provider can be supplied without
    installing an entry point. A provider that raises (or whose entry point
    fails to load) is skipped with a logged warning, so one broken package never
    wedges the aggregation.

    Both kinds (``"apt"`` and ``"script"``) aggregate through this one
    function. De-duplication is keyed by ``package`` name; on collision the FIRST
    provider wins (entry-point discovery order, then ``extra_providers``) and
    the duplicate is dropped with a logged warning -- matching ``discover_jobs``
    (provider-wins / first-wins). Returns specs sorted by package name.

    DETERMINISM GUARANTEE (contract): the result is deduped-by-package and
    sorted-by-package, so the set of names -- i.e. ``--list`` output -- is
    STABLE regardless of entry-point iteration order. Only the *metadata*
    (purpose / provider / apt_repo / kind / install_url) of a duplicated
    package depends on discovery order (first-wins). Leaves can therefore
    rely on a reproducible install set.

    NOTE for ``apt-get install $(... list)`` consumers: the ``list``
    subcommand emits ``kind="apt"`` names only, so a script-kind entry
    never lands on an apt command line. The full set (both kinds) is
    visible in the table view and ``--json``.
    """
    providers: list[Callable[[], list[SystemDepSpec]]] = []
    if include_entry_points:
        # include_entry_points=False is the unit-test isolation seam: it
        # aggregates ONLY extra_providers, so exact-list assertions stay
        # valid regardless of which real providers are installed in the
        # running env (scitex-dev itself now registers one: rsync).
        for ep in _iter_entry_points(ENTRY_POINT_GROUP):
            providers.append(_make_ep_provider(ep))
    if extra_providers:
        providers.extend(extra_providers)

    by_package: dict[str, SystemDepSpec] = {}
    for provider in providers:
        try:
            deps = provider()
        except Exception:
            _logger.warning(
                "Failed to load system deps from provider %r",
                provider,
                exc_info=True,
            )
            continue
        for dep in deps:
            if not isinstance(dep, SystemDepSpec):
                _logger.warning(
                    "Provider %r yielded a non-SystemDepSpec %r; skipping",
                    provider,
                    dep,
                )
                continue
            if dep.package in by_package:
                _logger.warning(
                    "Duplicate system dep %r ignored (first provider wins)",
                    dep.package,
                )
                continue
            by_package[dep.package] = dep

    return [by_package[pkg] for pkg in sorted(by_package)]


__all__ = [
    "SystemDepSpec",
    "ENTRY_POINT_GROUP",
    "INSTALL_KINDS",
    "discover_system_deps",
]

# EOF
