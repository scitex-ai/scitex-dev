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

__all__ = [
    "HOST_KINDS",
    "HostRecord",
    "HostRegistryError",
    "UnknownHostError",
    "create_default_hosts_yaml",
    "get_hosts_yaml_path",
    "list_hosts",
    "resolve",
]

# Closed set of host kinds. Extend deliberately — every consumer
# (sac / scitex-hub / scitex-storage) branches on this value, so a new
# kind is a cross-package agreement, not a one-line drive-by edit.
HOST_KINDS: frozenset[str] = frozenset({"workstation", "hpc-login", "storage"})

_ENV_HOSTS_YAML = "SCITEX_DEV_HOSTS_YAML"

# Seeded on first use (see `create_default_hosts_yaml`). Real host data
# from the operator's environment — names match the established
# convention already referenced across scitex-dev's own skills/docs
# (ywata-note-win, spartan, nas/nas1/nas2, mba).
_DEFAULT_HOSTS_YAML = """\
# SciTeX host registry — the shared port other scitex-* packages (sac,
# scitex-hub, scitex-storage, ...) resolve through instead of inventing
# their own host config. See `scitex_dev.hosts` for the Python API and
# `scitex-dev host --help` for the CLI.
#
# kind        : one of workstation, hpc-login, storage
# ssh_alias   : the ~/.ssh/config Host alias to reach this machine, or
#               null when the host IS local (no SSH hop needed)
# scitex_root : that HOST's $SCITEX_DIR (may use ~; expanded on that
#               host, not necessarily on the machine reading this file)

hosts:
  ywata-note-win:
    kind: workstation
    ssh_alias: null
    scitex_root: "~/.scitex"
  spartan:
    kind: hpc-login
    ssh_alias: spartan
    scitex_root: "/data/gpfs/projects/punim0264/ywatanabe/.scitex"
  nas:
    kind: storage
    ssh_alias: nas
    scitex_root: "~/.scitex"
  nas1:
    kind: storage
    ssh_alias: nas1
    scitex_root: "~/.scitex"
  nas2:
    kind: storage
    ssh_alias: nas2
    scitex_root: "~/.scitex"
  mba:
    kind: workstation
    ssh_alias: mba
    scitex_root: "~/.scitex"
"""


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
    """

    name: str
    kind: str
    ssh_alias: str | None
    scitex_root: str

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

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "kind": self.kind,
            "ssh_alias": self.ssh_alias,
            "scitex_root": self.scitex_root,
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


def _load_yaml(path: Path) -> dict:
    import yaml

    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise HostRegistryError(
            f"{path}: invalid YAML ({exc})",
            code=ErrorCode.VALIDATION,
            remediation=f"Fix the YAML syntax in {path}.",
        ) from exc


def _parse_host_record(name: str, data, *, hosts_path: Path) -> HostRecord:
    if not isinstance(data, dict):
        raise HostRegistryError(
            f"{hosts_path}: host {name!r} must be a mapping, got "
            f"{type(data).__name__}",
            code=ErrorCode.VALIDATION,
        )
    kind = data.get("kind")
    if not kind:
        raise HostRegistryError(
            f"{hosts_path}: host {name!r} is missing required field `kind`",
            code=ErrorCode.VALIDATION,
            remediation=f"Add `kind: <{'|'.join(sorted(HOST_KINDS))}>` to the {name!r} entry.",
        )
    scitex_root = data.get("scitex_root")
    if not scitex_root:
        raise HostRegistryError(
            f"{hosts_path}: host {name!r} is missing required field `scitex_root`",
            code=ErrorCode.VALIDATION,
            remediation=f"Add `scitex_root: <path>` to the {name!r} entry.",
        )
    try:
        return HostRecord(
            name=name,
            kind=kind,
            ssh_alias=data.get("ssh_alias"),
            scitex_root=str(scitex_root),
        )
    except HostRegistryError as exc:
        # Re-raise with the source file attached for a fully actionable
        # message (the dataclass itself doesn't know its own file path).
        raise HostRegistryError(
            f"{hosts_path}: {exc.message}",
            code=exc.error_code,
            remediation=exc.remediation,
        ) from exc


def _load_registry(
    hosts_path: str | Path | None = None,
) -> tuple[dict[str, HostRecord], Path]:
    path = get_hosts_yaml_path(hosts_path)
    if not path.exists():
        create_default_hosts_yaml(path)
    data = _load_yaml(path)
    raw_hosts = data.get("hosts") or {}
    if not isinstance(raw_hosts, dict):
        raise HostRegistryError(
            f"{path}: top-level `hosts:` must be a mapping of name -> record",
            code=ErrorCode.VALIDATION,
        )
    records = {
        name: _parse_host_record(name, entry, hosts_path=path)
        for name, entry in raw_hosts.items()
    }
    return records, path


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
        raise UnknownHostError(name, records.keys(), path) from None


# EOF
