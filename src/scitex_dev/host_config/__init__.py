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
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_logger = logging.getLogger(__name__)

#: Entry-point group every leaf registers its host-config provider under.
ENTRY_POINT_GROUP = "scitex_dev.host_config"

#: Per-item outcomes of :func:`evaluate`. See the docstring there --
#: ``drift`` is deliberately distinct from ``absent`` because the two
#: warrant opposite responses (converge vs report-and-leave-alone).
STATE_OK = "ok"
STATE_ABSENT = "absent"
STATE_DRIFT = "drift"
STATE_NOT_APPLICABLE = "not_applicable"


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
    requires_root
        Whether writing ``path`` needs root. Defaults to ``True``
        (anything under ``/etc`` does). CHECKING never needs root --
        that asymmetry is why the periodic job can run unprivileged.
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
    requires_root: bool = True

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
    by_path: dict[str, str] = {}
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
            if spec.path in by_path:
                _logger.warning(
                    "Host config %r targets %s, already claimed by %r -- "
                    "two declarations for one file will fight; ignoring the "
                    "second (first provider wins)",
                    spec.name,
                    spec.path,
                    by_path[spec.path],
                )
                continue
            by_name[spec.name] = spec
            by_path[spec.path] = spec.name

    return [by_name[name] for name in sorted(by_name)]


@dataclass(frozen=True)
class HostConfigStatus:
    """The result of comparing one ``HostConfigSpec`` against a host."""

    spec: HostConfigSpec
    state: str
    detail: str

    @property
    def needs_apply(self) -> bool:
        """Whether ``--apply`` would (be allowed to) change anything."""
        return self.state in (STATE_ABSENT, STATE_DRIFT)


def evaluate(
    spec: HostConfigSpec,
    *,
    root: str = "/",
    hostname: str | None = None,
) -> HostConfigStatus:
    """Compare ``spec`` against the live host WITHOUT changing anything.

    Pure observation -- never writes, never needs root, so the periodic
    job can run unprivileged and still be honest about what it sees.

    Four outcomes, and the split between the middle two is the whole
    point of this module:

    * ``not_applicable`` -- ``spec.hosts`` excludes this host.
    * ``ok`` -- file present, content byte-identical, mode as declared.
      A second run of a converged host reports this for everything;
      that IS the "second run is a no-op and says so" contract.
    * ``absent`` -- no file. Converging this is safe: nothing is being
      overwritten, so ``--apply`` creates it.
    * ``drift`` -- the file exists but differs. SOMEONE OR SOMETHING
      CHANGED IT. This is never silently corrected: it is reported, and
      overwriting it takes an explicit ``--force`` (which backs the old
      file up first). Quietly re-converging drift would destroy both
      the evidence and the reason it happened.

    ``root`` prefixes ``spec.path`` so tests can evaluate against a
    tmp_path instead of the real ``/etc``.
    """
    hostname = hostname if hostname is not None else socket.gethostname()
    if not spec.applies_to(hostname):
        return HostConfigStatus(
            spec,
            STATE_NOT_APPLICABLE,
            f"declared for {', '.join(spec.hosts)}; this host is {hostname}",
        )

    target = Path(root) / spec.path.lstrip("/")
    if not target.exists():
        return HostConfigStatus(spec, STATE_ABSENT, f"{spec.path} does not exist")

    try:
        actual = target.read_text(encoding="utf-8")
    except OSError as exc:
        # Unreadable is NOT "ok" and NOT "absent" -- we genuinely do not
        # know, and a success-shaped answer here would be the classic
        # "the check never ran" failure. Report it as drift so it stays
        # visible and never gets auto-overwritten.
        return HostConfigStatus(spec, STATE_DRIFT, f"{spec.path} unreadable: {exc}")

    actual_mode = oct(target.stat().st_mode & 0o777)[2:].zfill(4)
    want_mode = spec.mode.zfill(4)
    if actual != spec.content:
        return HostConfigStatus(
            spec,
            STATE_DRIFT,
            f"{spec.path} content differs from the declaration",
        )
    if actual_mode != want_mode:
        return HostConfigStatus(
            spec,
            STATE_DRIFT,
            f"{spec.path} mode is {actual_mode}, declared {want_mode}",
        )
    return HostConfigStatus(spec, STATE_OK, f"{spec.path} matches the declaration")


__all__ = [
    "HostConfigSpec",
    "HostConfigStatus",
    "ENTRY_POINT_GROUP",
    "STATE_OK",
    "STATE_ABSENT",
    "STATE_DRIFT",
    "STATE_NOT_APPLICABLE",
    "discover_host_config",
    "evaluate",
    "directives_of",
]


def directives_of(content: str) -> dict[str, str]:
    """Parse the EFFECTIVE ``key=value`` settings out of a config body.

    Comments are not settings. Without this, a test asserting "we do not
    leave ``Storage=auto``" matches the *explanation* of why auto is
    wrong, sitting in a comment two lines above ``Storage=persistent``
    -- a false failure that trains people to weaken the assertion. The
    parser keeps such tests honest by looking only at live directives.
    """
    out: dict[str, str] = {}
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";", "[")) or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out

# EOF
