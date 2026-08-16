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

import ipaddress
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
from ._seed import (
    _DEFAULT_HOSTS_YAML,
    packaged_default_requested_addresses,
    packaged_default_runner_destinations,
)

__all__ = [
    "HOST_KINDS",
    "HostRecord",
    "HostRegistryError",
    "UnknownHostError",
    "create_default_hosts_yaml",
    "find_runner_host",
    "get_hosts_yaml_path",
    "list_hosts",
    "list_requested_addresses",
    "list_runner_destinations",
    "packaged_default_requested_addresses",
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
        ``None`` when NO ALIAS IS RECORDED.

        ``None`` DOES NOT MEAN "this host is local". It used to, and that
        was a defect: **locality is not a property of a host, it is a
        RELATION between a host and whoever is asking.** A shared registry
        cannot store a relation in a field, because the field is written
        from one vantage point and read from many.

        Measured 2026-08-12: this registry was authored on the laptop,
        where ``ywata-note-win: ssh_alias: null`` correctly meant local.
        Read on scitex-compute-04 the same line asserts that the laptop IS
        this machine. Nothing about the file changed — only the reader did.
        A consumer inferring "no SSH hop needed" from it would run locally,
        silently, because "local" is a legitimate answer that raises
        nothing.

        Ask :func:`is_local` instead; it compares against the running
        host's own name at read time. Same discipline as
        ``scitex_dev.store``'s node identity, which comes from
        ``pg_control_system().system_identifier`` precisely so a COPIED
        file cannot lie about which machine it is on.
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
    requested_address : str | None
        The LAN address this machine should ASK its DHCP server for
        (DHCP option 50, "Requested IP Address"). ``None`` (the default)
        means the fleet expresses no preference for this host.

        THIS FIELD IS DESIRED STATE, AND ITS NAME IS THE WARNING. It is
        a request, not a reservation: the DHCP server may ignore it, and
        WILL ignore it when the address is already leased to something
        else. So it yields "usually this address", never "always", and a
        consumer that treats it as the host's address is wrong. The
        address a host currently HOLDS is a different fact, obtained by
        observing the host (``ip -4 -o addr show``), and is deliberately
        NOT stored here — a declaration that gets rewritten to match
        reality has stopped being a declaration.

        The gap between the two is therefore the PERMANENT, EXPECTED
        condition of this system, not an error state. Reporting it is
        the job of ``scitex-dev ecosystem host-config check``, which
        compares declared against observed; see
        :mod:`scitex_dev._host_config` for the per-host mechanism (and
        for the five fleet hosts that have no mechanism at all).

        Why declare it here rather than reserve it on the router: a
        router-side reservation table lives in the router's GUI, so
        replacing the router discards it and the topology has to be
        rediscovered by hand. Declared here, the map is code — it
        survives the swap, and it is reviewable.
    """

    name: str
    kind: str
    ssh_alias: str | None
    scitex_root: str
    runner_labels: tuple[frozenset[str], ...] = ()
    aliases: tuple[str, ...] = ()
    requested_address: str | None = None

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
        if self.requested_address is not None:
            # Validate at CONSTRUCTION, like `kind`, because this value is
            # rendered verbatim into a file that a DHCP client parses. A
            # typo'd address does not fail loudly at apply time -- the
            # client rejects the directive and silently keeps whatever
            # lease it had, which looks exactly like "the server ignored
            # our request". Catching it here keeps those two apart.
            try:
                ipaddress.IPv4Address(self.requested_address)
            except ValueError as exc:
                raise HostRegistryError(
                    f"host {self.name!r}: `requested_address` must be a "
                    f"literal IPv4 address, got {self.requested_address!r} "
                    f"({exc})",
                    code=ErrorCode.VALIDATION,
                ) from exc

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
            "requested_address": self.requested_address,
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

    Warns (never raises) for any row routing through a RETIRED ssh alias —
    see :mod:`scitex_dev.hosts._retired`. A registry frozen by the seeder
    before those names died still serves them, and only a runtime check
    reaches such a file.

    Parameters
    ----------
    hosts_path : str | Path | None
        Explicit override for the ``hosts.yaml`` location (see
        :func:`get_hosts_yaml_path` for the full precedence chain).
    """
    from ._retired import warn_if_retired

    records, _path = _load_registry(hosts_path)
    out = [records[name] for name in sorted(records)]
    for record in out:
        warn_if_retired(record.name, record.ssh_alias)
    return out


def list_runner_destinations(
    *, hosts_path: str | Path | None = None, include_packaged_floor: bool = True
) -> list[tuple[str, frozenset[str]]]:
    """Return every LEGAL CI runner destination the registry knows.

    One ``(host_name, label_set)`` pair per registered runner, sorted by
    host name. Hosts with no ``runner_labels`` contribute nothing.

    THE PACKAGED SEED IS A FLOOR, UNIONED IN BY DEFAULT. The user-state
    ``hosts.yaml`` is mutable per host and edited live, so it goes stale
    without any signal: this machine's copy was written 2026-08-05 and
    still recorded only Spartan on 2026-08-15, by which time the whole
    compute fleet was serving CI. A local file that is merely OLD must not
    be able to un-declare a runner the package knows exists, so the shipped
    seed is added rather than consulted as a fallback.

    That this was a REAL divergence and not a hypothetical one is the
    reason for the default: on 2026-08-15 this function answered ``None``
    for a destination four online machines were serving, while the PS-224
    audit rule — which already unioned the floor itself — answered
    correctly. ONE QUESTION MUST NOT HAVE TWO ANSWERS DEPENDING ON WHICH
    ENTRY POINT A CALLER HAPPENS TO REACH FOR.

    Pass ``include_packaged_floor=False`` for the narrower question "what
    does THIS FILE declare" — auditing the file itself, or reporting drift
    between it and the seed. It is the wrong default for "can this job be
    picked up", which is what every other caller is asking.

    An EMPTY result means NO runner destinations are known from either
    source — the registry gap, not a fleet of illegal workflows. Callers
    must distinguish the two: reporting every workflow as illegal because
    the registry was never populated would be a fleet-wide red for the
    wrong reason.
    """
    out: list[tuple[str, frozenset[str]]] = []
    for host in list_hosts(hosts_path=hosts_path):
        out.extend((host.name, labels) for labels in host.runner_labels)
    if include_packaged_floor:
        seen = set(out)
        out.extend(
            pair for pair in packaged_default_runner_destinations() if pair not in seen
        )
    return out


def list_requested_addresses(
    *, hosts_path: str | Path | None = None
) -> dict[str, str]:
    """Return the fleet's DESIRED LAN address map, ``{host name: IPv4}``.

    One entry per registered host that declares a
    :attr:`HostRecord.requested_address`; hosts with no preference
    contribute nothing.

    The shipped :func:`packaged_default_requested_addresses` map is the
    BASE and the on-disk registry OVERRIDES it per host — a MERGE, not an
    either/or, and the distinction matters.
    ``create_default_hosts_yaml`` only writes when the file is MISSING, so
    every host that already had a ``hosts.yaml`` before this field existed
    carries a copy with no addresses in it. Returning only what that file
    declares would let a stale local copy silently erase the fleet map on
    exactly the hosts that have been around longest — the per-host
    disappearance this map exists to survive. Taking only the packaged map
    would be the opposite failure: an address could never be corrected
    without a release.

    A host that has been re-keyed answers under its CANONICAL name here,
    not its aliases — the map is keyed for lookup, and emitting one
    address under several spellings would read as a collision.

    THE VALUES ARE REQUESTS, NOT FACTS. See
    :attr:`HostRecord.requested_address`: this is what each machine should
    ASK for, never what it currently holds.
    """
    merged = packaged_default_requested_addresses()
    for host in list_hosts(hosts_path=hosts_path):
        if host.requested_address:
            merged[host.name] = host.requested_address
    return merged


def find_runner_host(
    labels: Iterable[str],
    *,
    hosts_path: str | Path | None = None,
    include_packaged_floor: bool = True,
) -> HostRecord | None:
    """Return the first registered machine that serves ``labels``, else ``None``.

    "Serves" is GitHub's dispatch rule — a runner matches when its own
    label set CONTAINS every requested label (see
    :meth:`HostRecord.serves`). ``None`` means no registered machine can
    ever pick this job up: the job is not merely slow, it is undeliverable
    and will sit queued forever.

    The packaged seed is unioned in by default, for the reason given on
    :func:`list_runner_destinations` — a stale local file must not be able
    to report a live destination as undeliverable.

    ``None`` IS STILL NOT A LIVENESS ANSWER. This function reports whether
    a destination is DECLARED, never whether the machine is up: on
    2026-08-15 every Spartan runner was offline and ``spartan-cpu``
    resolved here perfectly well, while 57 jobs queued forever against it.
    Registration and availability are different questions and this registry
    only holds the first.
    """
    wanted = frozenset(labels)
    for host in list_hosts(hosts_path=hosts_path):
        if host.serves(wanted):
            return host
    if not include_packaged_floor:
        return None
    for name, declared in packaged_default_runner_destinations():
        if wanted <= declared:
            return _seed_record(name)
    return None


def _seed_record(name: str) -> HostRecord | None:
    """Return the packaged seed's record for ``name``, or ``None``.

    Used only when a destination matched the FLOOR rather than user state,
    so the caller still gets a ``HostRecord`` and not a bare name.
    """
    import yaml

    raw_hosts = (yaml.safe_load(_DEFAULT_HOSTS_YAML) or {}).get("hosts") or {}
    data = raw_hosts.get(name)
    if data is None:
        return None
    return _parse_host_record(name, data, hosts_path=Path("<packaged seed>"))


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
    from ._retired import warn_if_retired

    records, path = _load_registry(hosts_path)
    try:
        record = records[name]
    except KeyError:
        pass
    else:
        warn_if_retired(record.name, record.ssh_alias)
        return record

    # Fall back to ALIASES — a former or alternate spelling must keep
    # resolving, which is the whole reason the field exists. Canonical keys
    # are tried FIRST and exhaustively, so a name that is somebody's
    # canonical key can never be captured by another record's alias list.
    by_alias = [rec for rec in records.values() if name in rec.aliases]
    if len(by_alias) == 1:
        warn_if_retired(by_alias[0].name, by_alias[0].ssh_alias)
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
def is_local(record: "HostRecord | str") -> bool:
    """Whether ``record`` names the machine this process is running on.

    COMPUTED, never declared. The registry is shared across hosts, so no
    field in it can answer this: a stored value is written from one vantage
    point and read from many, and locality is a relation between the host
    and the reader rather than a property of the host.

    That is not hypothetical. Until 2026-08-12 ``ssh_alias: null`` was
    documented as meaning "this host is local". The file was authored on
    ``ywata-note-win``, where that was true, and is read on
    ``scitex-compute-04``, where it asserts that the laptop is this machine.

    Compares the host's canonical short name against this machine's, both
    reduced to the part before the first dot so a FQDN and a short name
    agree. Accepts a name directly so a caller holding only a string does
    not have to resolve a record to ask.
    """
    import socket

    name = record if isinstance(record, str) else record.name
    here = socket.gethostname()
    return name.split(".", 1)[0].casefold() == here.split(".", 1)[0].casefold()


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
