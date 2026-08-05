#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SciTeX host registry — engine.

Implements the design shared with sac (scitex-agent-container),
scitex-hub, and scitex-storage: a single place that answers "where is
host X, and what's its ``~/.scitex`` root path?" — instead of every
package inventing (or hardcoding) its own answer.

Background (the incident this fixes)
-------------------------------------
sac currently owns this ad hoc in ``~/.scitex/agent-container/config.yaml``.
Separately, a host-specific absolute path
(``/data/gpfs/projects/punim0264/ywatanabe/.scitex``, Spartan-only) was
committed as a literal git-tracked SYMLINK at ``src/.scitex`` in the
shared dotfiles repo — so every non-Spartan host that checks out that
commit gets a DANGLING symlink at ``~/.scitex``, the path where the
ENTIRE fleet's config/runtime state lives. That already silently broke
config delivery to a NAS host. The fix: hosts resolve each other's
paths through this registry, never a hardcoded path baked into version
control.

Data nature: hosts.yaml is a DATA/STATE store (the canonical mutable
registry), not CONFIG — per
``01_ecosystem/12_local-state-resolution.md`` it is resolved with
``local_state.user_path()`` so a stray project-scope
``<repo>/.scitex/dev/hosts.yaml`` can never shadow the canonical
record.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .._core.errors import ErrorCode, ScitexError

# The shipped default seed + its runner destinations live in `._seed`
# (extracted so this engine module stays focused and under the file-size
# limit). `_DEFAULT_HOSTS_YAML` is re-imported because
# `create_default_hosts_yaml` writes it on first use;
# `packaged_default_runner_destinations` is re-exported for PS-224's floor.
from ._seed import _DEFAULT_HOSTS_YAML, packaged_default_runner_destinations

__all__ = [
    "HOST_KINDS",
    "HostRecord",
    "HostRegistryError",
    "UnknownHostError",
    "create_default_hosts_yaml",
    "find_runner_host",
    "get_hosts_yaml_path",
    "list_hosts",
    "list_runner_destinations",
    "packaged_default_runner_destinations",
    "resolve",
]

# Closed set of host kinds. Extend deliberately — every consumer
# (sac / scitex-hub / scitex-storage) branches on this value, so a new
# kind is a cross-package agreement, not a one-line drive-by edit.
#
# THE AXIS IS HOW WORK REACHES THE MACHINE, NOT HOW BIG IT IS.
# That is what a consumer actually branches on, so it is what distinguishes
# the members:
#
#   workstation  someone's personal machine. May be asleep, may be behind a
#                laptop lid. Work is not placed here by anyone but its owner.
#   hpc-login    a login node fronting a SCHEDULER. You do not run work here;
#                you SUBMIT it, and something else decides when it runs.
#   compute      shared, always-on infrastructure reached DIRECTLY — ssh in
#                and run. No scheduler, no queue, no module system.
#   storage      a machine that holds data rather than executing work.
#
# `compute` vs `hpc-login` is the distinction most likely to be collapsed, so
# it is worth stating why it must not be. Both are "big machines that run
# things", but a consumer deciding whether it may simply START a job needs
# opposite answers: on `hpc-login` it must submit and wait; on `compute` it
# runs now. Sizing them by core count would put them in the same bucket and
# lose exactly the fact anyone needs. (scitex-storage independently arrived
# at a scheduler-flavoured word for its own vocabulary, `hpc-compute`, which
# names a node reached THROUGH a scheduler — a different thing from this.)
#
# `compute` added 2026-08-05 for scitex-compute-01/02, measured by scitex-hpc:
# 32 cores each, Ubuntu 24.04.4, Apptainer 1.5.3, and NO sbatch, NO sinfo,
# slurmd inactive, no module system. `workstation` parses for them and is
# wrong — they are shared headless infrastructure, not somebody's desk — and
# a wrong kind is worse than a missing one because it answers confidently.
HOST_KINDS: frozenset[str] = frozenset(
    {"workstation", "hpc-login", "compute", "storage"}
)

_ENV_HOSTS_YAML = "SCITEX_DEV_HOSTS_YAML"


class HostRegistryError(ScitexError):
    """``hosts.yaml`` is malformed (bad shape, bad `kind`, YAML parse error)."""


class UnknownHostError(ScitexError):
    """``resolve()`` was asked for a host that isn't registered.

    Fails loud, no silent fallback (this repo's constitution) — carries
    the full list of registered hosts plus the file to edit so the
    caller (human or agent) can fix it in one step.
    """

    def __init__(self, name: str, known: Iterable[str], hosts_path: Path) -> None:
        known_sorted = sorted(known)
        listing = ", ".join(known_sorted) if known_sorted else "(none registered)"
        message = f"Unknown host {name!r}. Registered hosts: {listing}."
        remediation = (
            f"Add a `{name}:` entry to {hosts_path}, or check for a typo "
            f"against one of: {listing}."
        )
        super().__init__(message, code=ErrorCode.CONFIG, remediation=remediation)
        self.name = name
        self.known = known_sorted
        self.hosts_path = hosts_path


@dataclass(frozen=True)
class HostRecord:
    """One entry in the SciTeX host registry.

    Attributes
    ----------
    name : str
        The host's canonical short name (e.g. ``"spartan"``) — matches
        its top-level key in ``hosts.yaml``.
    kind : str
        One of :data:`HOST_KINDS`.
    ssh_alias : str | None
        The ``~/.ssh/config`` ``Host`` alias to reach this machine, or
        ``None`` when the host is local / needs no SSH hop.
    scitex_root : str
        The raw (possibly ``~``-prefixed) path to this host's
        ``$SCITEX_DIR``. Use :attr:`scitex_root_path` for the expanded
        :class:`~pathlib.Path` — expansion is deliberately deferred to
        resolve time (see the property docstring for the caveat about
        *whose* home directory it expands against).
    aliases : tuple[str, ...]
        FORMER or ALTERNATE spellings of :attr:`name` that must keep
        resolving to this record. Empty (the default) means the canonical
        name is the only one.

        This exists so a host can be RE-KEYED without orphaning whatever
        already referenced the old spelling. Host names are on-disk KEYS —
        cron entries, JobSpecs, sync configs, other packages' registry rows,
        card scopes — and rewriting a key silently orphans every one of those.
        The orphan renders as "nothing to do" rather than as an error, which
        is why it is worth a schema field rather than a migration note.

        The motivating case: the fleet's NAS numbering is GENERATIONAL
        (``nas-01`` / ``nas-02`` / ``nas-03`` ascend as machines are
        REPLACED), and the bare name ``nas`` follows whatever is current. So
        ``nas`` is a MOVING ALIAS: the day a ``nas-04`` arrives, every config
        keyed on ``nas`` addresses different physical hardware, with nothing
        logged and nothing failing. A name that resolves is not an identity
        that stays put.

        A moving alias therefore belongs HERE and never in :attr:`name` — it
        is a way to reach the host, not a way to identify it.
    runner_labels : tuple[frozenset[str], ...]
        The CI RUNNER DESTINATIONS this machine serves: one
        :class:`frozenset` of labels per distinct self-hosted GitHub
        Actions runner registered from this machine. Empty (the default)
        means the machine hosts no CI runner.

        Each entry is the runner's EFFECTIVE label set — the labels
        GitHub auto-assigns (``self-hosted`` / OS / arch) included, so it
        matches what the Actions API reports verbatim.

        A destination is served by this machine iff some entry is a
        SUPERSET of the requested labels — that is GitHub's own
        dispatch rule, and modelling it per-runner (rather than as one
        flat per-machine union) is what keeps the check exact: a union
        would green-light a combination that no single runner offers.
    """

    name: str
    kind: str
    ssh_alias: str | None
    scitex_root: str
    runner_labels: tuple[frozenset[str], ...] = ()
    aliases: tuple[str, ...] = ()

    def serves(self, labels: Iterable[str]) -> bool:
        """True iff one of this host's runners carries every label in ``labels``.

        Mirrors GitHub's dispatch rule: a job is routed to a runner whose
        label set CONTAINS every label the job requested. An empty
        ``labels`` request is never served — a job must name a
        destination, and "no labels at all" names nothing.
        """
        wanted = frozenset(labels)
        if not wanted:
            return False
        return any(wanted <= served for served in self.runner_labels)

    def __post_init__(self) -> None:
        if self.kind not in HOST_KINDS:
            raise HostRegistryError(
                f"host {self.name!r}: invalid kind {self.kind!r} "
                f"(must be one of: {', '.join(sorted(HOST_KINDS))})",
                code=ErrorCode.VALIDATION,
            )

    @property
    def scitex_root_path(self) -> Path:
        """Expand ``scitex_root`` (``~`` and env vars) to a concrete path.

        Expands against *this process's* home directory / environment.
        For a remote host reached via :attr:`ssh_alias`, that is only
        meaningful when this code is actually running *on* that host
        (e.g. inside an ``ssh <alias> ...`` invocation) — evaluated
        locally it tells you nothing about the remote filesystem.
        """
        return Path(os.path.expandvars(self.scitex_root)).expanduser()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "ssh_alias": self.ssh_alias,
            "scitex_root": self.scitex_root,
            "runner_labels": [sorted(s) for s in self.runner_labels],
            "aliases": list(self.aliases),
        }


def get_hosts_yaml_path(hosts_path: str | Path | None = None) -> Path:
    """Resolve the ``hosts.yaml`` path.

    Precedence (highest first): explicit ``hosts_path`` argument →
    ``$SCITEX_DEV_HOSTS_YAML`` → the DATA/STATE-store canonical location
    ``local_state.user_path("dev", "hosts.yaml")``. The user-path
    resolver is deliberate — a stray project-scope
    ``<repo>/.scitex/dev/hosts.yaml`` must never shadow the canonical
    fleet-wide registry (the anti-footgun rule in
    ``01_ecosystem/12_local-state-resolution.md``).
    """
    if hosts_path is not None:
        return Path(hosts_path).expanduser()
    env_override = os.environ.get(_ENV_HOSTS_YAML, "").strip()
    if env_override:
        return Path(env_override).expanduser()

    from scitex_config._ecosystem import local_state

    return local_state.user_path("dev", "hosts.yaml")


def create_default_hosts_yaml(hosts_path: str | Path | None = None) -> Path:
    """Seed ``hosts.yaml`` with the known operator hosts if it doesn't exist.

    Idempotent — a no-op when the file already exists. Mirrors
    ``scitex_dev._core.config.create_default_config``'s first-run
    seeding pattern for consistency across the package's config
    surfaces.
    """
    path = get_hosts_yaml_path(hosts_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    path.write_text(_DEFAULT_HOSTS_YAML)
    return path


def list_hosts(*, hosts_path: str | Path | None = None) -> list[HostRecord]:
    """Return every registered host, sorted by name.

    Parameters
    ----------
    hosts_path : str | Path | None
        Explicit override for the ``hosts.yaml`` location (see
        :func:`get_hosts_yaml_path` for the full precedence chain).
    """
    records, _path = _load_registry(hosts_path)
    return [records[name] for name in sorted(records)]


def list_runner_destinations(
    *, hosts_path: str | Path | None = None
) -> list[tuple[str, frozenset[str]]]:
    """Return every LEGAL CI runner destination the registry knows.

    One ``(host_name, label_set)`` pair per registered runner, sorted by
    host name. Hosts with no ``runner_labels`` contribute nothing.

    An EMPTY result means the registry records no runner destinations at
    all — the registry gap, not a fleet of illegal workflows. Callers
    (notably the PS-224 audit rule) must distinguish the two: reporting
    every workflow as illegal because the registry was never populated
    would be a fleet-wide red for the wrong reason.
    """
    out: list[tuple[str, frozenset[str]]] = []
    for host in list_hosts(hosts_path=hosts_path):
        out.extend((host.name, labels) for labels in host.runner_labels)
    return out


def find_runner_host(
    labels: Iterable[str], *, hosts_path: str | Path | None = None
) -> HostRecord | None:
    """Return the first registered machine that serves ``labels``, else ``None``.

    "Serves" is GitHub's dispatch rule — a runner matches when its own
    label set CONTAINS every requested label (see
    :meth:`HostRecord.serves`). ``None`` means no registered machine can
    ever pick this job up: the job is not merely slow, it is undeliverable
    and will sit queued forever.
    """
    wanted = frozenset(labels)
    for host in list_hosts(hosts_path=hosts_path):
        if host.serves(wanted):
            return host
    return None


def resolve(name: str, *, hosts_path: str | Path | None = None) -> HostRecord:
    """Resolve a host by name.

    Parameters
    ----------
    name : str
        The host's registered short name (e.g. ``"spartan"``).
    hosts_path : str | Path | None
        Explicit override for the ``hosts.yaml`` location (see
        :func:`get_hosts_yaml_path` for the full precedence chain).

    Raises
    ------
    UnknownHostError
        If ``name`` is not a key in the registry — fails loud, no
        silent fallback (this repo's constitution).
    HostRegistryError
        If ``hosts.yaml`` itself is malformed.
    """
    records, path = _load_registry(hosts_path)
    try:
        return records[name]
    except KeyError:
        pass

    # Fall back to ALIASES — a former or alternate spelling must keep
    # resolving, which is the whole reason the field exists. Canonical keys
    # are tried FIRST and exhaustively, so a name that is somebody's
    # canonical key can never be captured by another record's alias list.
    by_alias = [rec for rec in records.values() if name in rec.aliases]
    if len(by_alias) == 1:
        return by_alias[0]
    if by_alias:
        claimants = ", ".join(sorted(rec.name for rec in by_alias))
        raise HostRegistryError(
            f"{path}: {name!r} is claimed as an alias by more than one host "
            f"({claimants}). An alias must identify exactly one machine — "
            "resolving it would be a guess, and a guess about which host to "
            "reach is how a command lands on the wrong box.",
            code=ErrorCode.VALIDATION,
            remediation=(
                f"Remove {name!r} from every `aliases:` list but one in "
                f"{path}."
            ),
        )
    raise UnknownHostError(name, records.keys(), path) from None


# Re-exported so existing imports (`from ._registry import _load_registry`)
# keep resolving after the split. Imported at the BOTTOM, after `HostRecord`
# is defined, because `._parse` imports it back — a top-of-file import would
# close the cycle.
from ._parse import (  # noqa: E402
    _load_registry,
    _load_yaml,
    _parse_aliases,
    _parse_host_record,
    _parse_runner_labels,
)

# EOF
