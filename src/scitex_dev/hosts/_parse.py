# -*- coding: utf-8 -*-
"""Read and validate `hosts.yaml` — deserialization only.

Split out of `_registry` (512-line budget), and the seam is real rather than
arbitrary: this module changes when the FILE FORMAT changes, while `_registry`
changes when the host CONTRACT does. Nothing outside the package imports these
names; `_registry` re-exports them so existing imports and tests resolve
unchanged.

Every parser here FAILS on a malformed value rather than degrading to a
default. A field that silently parses to empty is how a registry ends up
quietly describing a machine nobody meant — and for `aliases` specifically it
is how a re-keyed host stops answering to its old name with no error at all.
"""

from __future__ import annotations

from pathlib import Path

from .._core.errors import ErrorCode
from ._connectivity import (
    HostConnectivity,
    NetRoute,
    normalize_fingerprint,
    normalize_mac,
    reject_key_material,
)
from ._registry import (
    HOST_KINDS,
    HostRecord,
    HostRegistryError,
    create_default_hosts_yaml,
    get_hosts_yaml_path,
)

#: Keys recognised inside a host's ``net:`` block. A CLOSED set, unlike the
#: host record itself: ``net:`` is brand new, so nothing in the wild has
#: extras to preserve, and a typo'd key there (``proxycommand`` for
#: ``proxy_command``) would silently render a stanza with no proxy — a name
#: that resolves and cannot connect.
_NET_KEYS = frozenset({"transport", "hostname", "port", "jump", "proxy_command"})

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


def _parse_runner_labels(
    name: str, raw, *, hosts_path: Path
) -> tuple[frozenset[str], ...]:
    """Parse a host's ``runner_labels:`` block into label SETS.

    Shape: a list of lists of strings — one inner list per distinct
    self-hosted runner on the machine. Absent / ``null`` / ``[]`` means
    the machine hosts no CI runner, which is the common case (a NAS or a
    laptop) and is NOT an error.

    Fails loud on a malformed block rather than degrading to "no runners"
    — silently reading a typo'd registry as an empty one would turn every
    workflow in the fleet into a PS-224 error for a reason that has
    nothing to do with the workflows.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise HostRegistryError(
            f"{hosts_path}: host {name!r}: `runner_labels` must be a list of "
            f"label lists, got {type(raw).__name__}",
            code=ErrorCode.VALIDATION,
            remediation=(
                f"Write `runner_labels:` as a list of lists, e.g.\n"
                f"  runner_labels:\n"
                f"    - [self-hosted, Linux, X64, scitex-ci]"
            ),
        )
    sets: list[frozenset[str]] = []
    for entry in raw:
        if isinstance(entry, str) or not isinstance(entry, list):
            raise HostRegistryError(
                f"{hosts_path}: host {name!r}: each `runner_labels` entry must "
                f"be a LIST of label strings (one per runner), got "
                f"{type(entry).__name__} {entry!r}",
                code=ErrorCode.VALIDATION,
                remediation=(
                    "A bare string is ambiguous — a runner always carries a "
                    "SET of labels. Wrap it: `- [self-hosted, Linux, X64, "
                    "scitex-ci]`."
                ),
            )
        labels = {str(label).strip() for label in entry if str(label).strip()}
        if not labels:
            raise HostRegistryError(
                f"{hosts_path}: host {name!r}: empty `runner_labels` entry",
                code=ErrorCode.VALIDATION,
                remediation=(
                    "Delete the empty entry, or give the runner its labels. A "
                    "runner with no labels serves no destination."
                ),
            )
        sets.append(frozenset(labels))
    return tuple(sets)


def _parse_aliases(name: str, raw, *, hosts_path: Path) -> tuple[str, ...]:
    """Parse a host's ``aliases:`` list — former/alternate spellings.

    Absent is the norm and yields ``()``. A MALFORMED value FAILS rather than
    degrading to empty: an alias list that silently parsed to nothing would
    let a re-keyed host stop answering to its old name with no error at all,
    which is precisely the silent orphan the field exists to prevent.
    """
    if raw is None:
        return ()
    if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
        raise HostRegistryError(
            f"{hosts_path}: host {name!r}: `aliases` must be a LIST of names, "
            f"got {type(raw).__name__}. A bare string is REJECTED rather than "
            "wrapped: `aliases: nas-03` reads as one alias to a human, but "
            "iterating a string yields its characters, so the helpful "
            "interpretation and the literal one disagree.",
            code=ErrorCode.VALIDATION,
            remediation=f"Write `aliases: [{raw!r}]` for the {name!r} entry.",
        )
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise HostRegistryError(
                f"{hosts_path}: host {name!r}: every entry in `aliases` must "
                f"be a non-empty string, got {item!r}",
                code=ErrorCode.VALIDATION,
            )
        alias = item.strip()
        if alias == name:
            raise HostRegistryError(
                f"{hosts_path}: host {name!r} lists its own canonical name in "
                "`aliases`. That is not harmful so much as meaningless, and it "
                "hides whether the author meant a DIFFERENT spelling.",
                code=ErrorCode.VALIDATION,
                remediation=f"Remove {alias!r} from the {name!r} alias list.",
            )
        out.append(alias)
    return tuple(out)


def _parse_net_route(name: str, raw, *, hosts_path: Path) -> NetRoute | None:
    """Parse a host's ``net:`` block — the route that LEAVES the LAN.

    Absent yields ``None``, which is the common case: most machines are
    LAN-only and have no off-LAN name at all.

    An UNKNOWN key raises. That is stricter than the rest of this file
    deliberately — see :data:`_NET_KEYS`. It is also the enforcement point
    for the naming rule's negative half: there is no way to express a
    bastion route anywhere except inside ``net:``, so a bare ``Host <name>``
    stanza structurally cannot acquire one.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise HostRegistryError(
            f"{hosts_path}: host {name!r}: `net` must be a mapping "
            f"(transport/hostname/port/jump/proxy_command), got "
            f"{type(raw).__name__}",
            code=ErrorCode.VALIDATION,
            remediation=(
                "Write it as e.g.\n"
                "  net:\n"
                "    transport: cloudflared\n"
                "    hostname: bastion.scitex.ai"
            ),
        )
    reject_key_material(name, raw, where="`net`")
    unknown = sorted(set(map(str, raw)) - _NET_KEYS)
    if unknown:
        raise HostRegistryError(
            f"{hosts_path}: host {name!r}: unknown key(s) in `net`: "
            f"{', '.join(unknown)}",
            code=ErrorCode.VALIDATION,
            remediation=(
                f"Valid keys: {', '.join(sorted(_NET_KEYS))}. A typo here "
                "renders a stanza with no proxy — a name that resolves and "
                "cannot connect — so it is rejected rather than ignored."
            ),
        )
    transport = raw.get("transport")
    if not transport:
        raise HostRegistryError(
            f"{hosts_path}: host {name!r}: `net` is missing `transport`",
            code=ErrorCode.VALIDATION,
            remediation="Add e.g. `transport: cloudflared` to the `net` block.",
        )
    port = raw.get("port")
    if port is not None and not isinstance(port, int):
        raise HostRegistryError(
            f"{hosts_path}: host {name!r}: `net.port` must be an integer, got "
            f"{port!r}",
            code=ErrorCode.VALIDATION,
        )
    try:
        return NetRoute(
            transport=str(transport).strip(),
            hostname=_opt_str(raw.get("hostname")),
            port=port,
            jump=_opt_str(raw.get("jump")),
            proxy_command=_opt_str(raw.get("proxy_command")),
        )
    except HostRegistryError as exc:
        raise HostRegistryError(
            f"{hosts_path}: host {name!r}: {exc.message}",
            code=exc.error_code,
            remediation=exc.remediation,
        ) from exc


def _opt_str(value) -> str | None:
    """``None`` for absent/blank, otherwise the stripped string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_connectivity(name: str, data, *, hosts_path: Path) -> HostConnectivity:
    """Read the connectivity fields off a host entry.

    Every field is optional and read from the host record's TOP level (not a
    nested block) except ``net:``, so a pre-existing entry parses to an empty
    :class:`HostConnectivity` and means exactly what it always meant.

    ``lan`` and ``reserved`` are read into SEPARATE fields and neither is
    allowed to stand in for the other. Measured 2026-08-13: three compute
    hosts are reserved at one address and answering at another because the
    leases have not renewed. Defaulting one from the other would manufacture
    a fact nobody observed.
    """
    reject_key_material(name, data, where="the host record")
    return HostConnectivity(
        lan=_opt_str(data.get("lan")),
        reserved=_opt_str(data.get("reserved")),
        net=_parse_net_route(name, data.get("net"), hosts_path=hosts_path),
        mac=normalize_mac(name, data.get("mac")),
        host_key_fingerprint=normalize_fingerprint(data.get("host_key_fingerprint")),
        reported_hostname=_opt_str(data.get("reported_hostname")),
        ssh_user=_opt_str(data.get("ssh_user")),
        identity_file=_opt_str(data.get("identity_file")),
        last_seen=_opt_str(data.get("last_seen")),
    )


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
            runner_labels=_parse_runner_labels(
                name, data.get("runner_labels"), hosts_path=hosts_path
            ),
            aliases=_parse_aliases(name, data.get("aliases"), hosts_path=hosts_path),
            connectivity=_parse_connectivity(name, data, hosts_path=hosts_path),
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



# EOF
