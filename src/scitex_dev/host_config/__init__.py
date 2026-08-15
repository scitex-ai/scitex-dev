#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/host_config/__init__.py
"""Federated HOST-LEVEL configuration declaration for the SciTeX ecosystem.

Every scitex leaf declares the *host* state it needs -- a journald
drop-in, a sysctl setting, a logrotate rule -- by registering a callable
under the ``scitex_dev.host_config`` entry-point group;
``discover_host_config()`` aggregates them. This is the same entry-point
federation used by ``scitex_dev.jobs`` / ``discover_jobs`` and
``scitex_dev.system_deps`` / ``discover_system_deps``, applied to the one
remaining layer that was still being configured by hand.

WHY A DECLARATION AND NOT AN ad-hoc ``sudo`` SESSION
----------------------------------------------------
Operator ruling, 2026-08-12: privileged host changes typed into a shell
leave no record, so months later nobody can tell *intent* from *drift* --
which of the current settings were deliberate, and which are the residue
of a forgotten debugging session. A declaration is a file someone can
read, diff and review; the applier is idempotent; and what it changed is
reported rather than silently converged.

Each ``HostConfigSpec`` is deliberately ONE primitive -- "this file must
exist with exactly this content" -- because that primitive is
checkable without root, diffable, and covers the drop-in directories
(``/etc/systemd/*.conf.d/``, ``/etc/sysctl.d/``, ``/etc/logrotate.d/``,
``/etc/security/limits.d/``) that modern Linux uses for exactly this
purpose. A spec that needs a daemon to notice the new file carries an
``apply_command``; a spec that can PROVE its effect by observation
carries a ``verify_command`` (see the field docs -- observation is the
only accepted proof that a host config actually took).

Example provider (in a leaf package)::

    # scitex_agent_container/_host_config.py
    from scitex_dev.host_config import HostConfigSpec

    def provide() -> list[HostConfigSpec]:
        return [
            HostConfigSpec(
                name="sac.tmpfiles-state",
                path="/etc/tmpfiles.d/scitex-agent-state.conf",
                content="d /state 0755 ywatanabe ywatanabe -\\n",
                purpose="agent state dir survives reboot",
                provider="scitex-agent-container",
                apply_command="systemd-tmpfiles --create",
            ),
        ]

    # pyproject.toml
    # [project.entry-points."scitex_dev.host_config"]
    # scitex-agent-container = "scitex_agent_container._host_config:provide"

``scitex-dev ecosystem host-config`` then surfaces, checks and (with
root) applies the declaration automatically.
"""

from __future__ import annotations

import logging
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ._volatility import volatile_reason

_logger = logging.getLogger(__name__)

#: Entry-point group every leaf registers its host-config provider under.
ENTRY_POINT_GROUP = "scitex_dev.host_config"

#: Per-item outcomes of :func:`evaluate`. See the docstring there --
#: ``drift`` is deliberately distinct from ``absent`` because the two
#: warrant opposite responses (converge vs report-and-leave-alone).


@dataclass(frozen=True)
class HostConfigSpec:
    """One file a scitex package requires a HOST to have, verbatim.

    Fields
    ------
    name
        Package-prefixed unique id, e.g. ``"journald.persistent"``.
        Mirrors ``JobSpec.name``: it makes the owning package obvious in
        listings and is the de-duplication key.
    path
        Absolute path of the managed file, e.g.
        ``"/etc/systemd/journald.conf.d/99-scitex-persistent.conf"``.
        Prefer a drop-in directory over editing a distro-owned file: a
        drop-in is additive, removable, and never collides with a
        package upgrade.
    content
        The EXACT desired file body, including the trailing newline.
        Equality against this string is the whole definition of "in
        the declared state" -- there is no partial/merge semantics,
        because a merge cannot be diffed or reasoned about later.
    purpose
        Short human-readable reason, shown in listings and docs. Say
        WHY, not what -- the what is already the content.
    provider
        The declaring package (e.g. ``"scitex-dev"``).
    hosts
        Hostnames this spec applies to. Empty (the default) means EVERY
        host. A non-empty tuple restricts it, and a host outside the
        tuple evaluates to ``not_applicable`` rather than ``absent`` --
        so a laptop-only tweak never shows up as drift on a server.
    mode
        Octal permission string for the file, e.g. ``"0644"``. Checked
        as well as content: a correct file nobody can read is not in
        the declared state.
    apply_command
        Shell command that makes a daemon NOTICE the new file, e.g.
        ``"systemctl restart systemd-journald"``. Run only after the
        file actually changed -- never on a no-op pass, so a periodic
        job does not restart a daemon every time it runs. ``None`` when
        the file is read on demand and no reload is needed.
    verify_command
        Shell command whose OUTPUT demonstrates the config took effect,
        independent of the file's own content. This is the
        anti-tautology field: reading back the file you just wrote
        proves nothing, so a spec that can be observed should say how.
        For journald persistence that is ``journalctl --list-boots``
        (more than one boot listed = the journal demonstrably survived
        a reboot). ``None`` when no observation is available.

        PICK A COMMAND A NORMAL USER CAN RUN. The periodic check is
        unprivileged by design, and a verifier that needs privileges it
        does not have returns a permission error that reads exactly like
        a finding. ``ip -4 -o addr show`` is readable by anyone;
        ``networkctl cat <iface>`` is not, because netplan's generated
        units are 0640 root:systemd-network. When no unprivileged
        equivalent exists, say so with ``verify_requires_root`` rather
        than shipping a command that always fails.
    verify_requires_root
        Whether ``verify_command`` needs root to produce a real answer
        -- ``auditctl -l`` reads the kernel's audit rules and needs
        CAP_AUDIT_CONTROL, so an unprivileged run reports a permission
        error rather than the ruleset. When set and the caller is not
        root, the observation is reported as ``not-observed`` with the
        reason, instead of running the command and recording a failure
        that looks like a finding. Defaults to ``False``.
    requires_root
        Whether writing ``path`` needs root. Defaults to ``True``
        (anything under ``/etc`` does). CHECKING never needs root --
        that asymmetry is why the periodic job can run unprivileged.
    requires_command
        A binary that must exist for this file to MEAN anything, e.g.
        ``"auditctl"`` for a file under ``/etc/audit/rules.d/``. When
        it is absent the spec evaluates to ``precondition_unmet`` and
        ``apply`` refuses to write.

        This exists because the alternative is worse than useless.
        Dropping a rules file onto a host whose daemon is not installed
        produces a file that is present, correct, and read by nothing --
        and every subsequent ``check`` would report ``ok``. That is a
        guard which cannot detect the thing it was installed for, while
        reporting that it can. ``None`` (the default) means the file
        stands on its own.
    """

    name: str
    path: str
    content: str
    purpose: str
    provider: str
    hosts: tuple[str, ...] = ()
    mode: str = "0644"
    apply_command: str | None = None
    verify_command: str | None = None
    verify_requires_root: bool = False
    requires_root: bool = True
    requires_command: str | None = None

    def __post_init__(self) -> None:
        # Fail EARLY at construction, exactly like SystemDepSpec and
        # JobSpec, so a malformed declaration can never reach an
        # applier that is about to write to /etc as root.
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                f"HostConfigSpec.name must be a non-empty id; got {self.name!r}"
            )
        if not isinstance(self.path, str) or not self.path.startswith("/"):
            raise ValueError(
                f"HostConfigSpec({self.name!r}).path must be an ABSOLUTE path; "
                f"got {self.path!r}"
            )
        if not isinstance(self.content, str) or not self.content:
            raise ValueError(
                f"HostConfigSpec({self.name!r}).content must be non-empty -- an "
                f"empty declaration cannot be distinguished from 'no opinion'."
            )
        if not self.content.endswith("\n"):
            # A config file without a trailing newline is a POSIX text-file
            # violation that several parsers silently truncate, and it makes
            # every future diff noisy. Reject at declaration time.
            raise ValueError(
                f"HostConfigSpec({self.name!r}).content must end with a newline."
            )
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError(
                f"HostConfigSpec({self.name!r}).provider must name the "
                f"declaring package; got {self.provider!r}"
            )
        if not isinstance(self.mode, str) or not self.mode.isdigit():
            raise ValueError(
                f"HostConfigSpec({self.name!r}).mode must be an octal string "
                f"like '0644'; got {self.mode!r}"
            )

    def applies_to(self, hostname: str) -> bool:
        """Whether this spec targets ``hostname``. Empty ``hosts`` = all."""
        return not self.hosts or hostname in self.hosts


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



# --------------------------------------------------------------------- #
# Public surface. Evaluation lives in `_evaluate` and the state          #
# vocabulary in `_states`; both are re-exported here so every existing   #
# `from scitex_dev.host_config import ...` keeps working unchanged.      #
# --------------------------------------------------------------------- #
from ._evaluate import HostConfigStatus, directives_of, evaluate  # noqa: E402
from ._states import (  # noqa: E402
    STATE_ABSENT,
    STATE_DRIFT,
    STATE_NOT_APPLICABLE,
    STATE_OK,
    STATE_PRECONDITION_UNMET,
)

__all__ = [
    "ENTRY_POINT_GROUP",
    "HostConfigSpec",
    "HostConfigStatus",
    "STATE_ABSENT",
    "STATE_DRIFT",
    "STATE_NOT_APPLICABLE",
    "STATE_OK",
    "STATE_PRECONDITION_UNMET",
    "directives_of",
    "discover_host_config",
    "evaluate",
]

# EOF
