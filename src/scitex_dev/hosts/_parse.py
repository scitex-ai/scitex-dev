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
from ._registry import (
    HOST_KINDS,
    HostRecord,
    HostRegistryError,
    create_default_hosts_yaml,
    get_hosts_yaml_path,
)

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


def _parse_requested_address(name: str, raw, *, hosts_path: Path) -> str | None:
    """Parse a host's ``requested_address:`` — the DHCP address it asks for.

    Absent / ``null`` is the norm and yields ``None`` ("this host has no
    declared preference"). The VALUE is validated by
    :class:`HostRecord` itself; this parser only rejects the shapes YAML
    can produce that a literal address never is.

    The interesting one is an UNQUOTED address. YAML leaves
    ``192.168.11.174`` a string (three dots is not a number), but a
    two-octet typo like ``192.168`` parses as a FLOAT, and
    ``requested_address: 011`` as an int. Coercing those with ``str()``
    would turn a typo into a plausible-looking address and write it into
    a DHCP client's config; rejecting the type is how the typo stays
    visible.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise HostRegistryError(
            f"{hosts_path}: host {name!r}: `requested_address` must be a "
            f"quoted IPv4 string, got {type(raw).__name__} {raw!r}. YAML "
            "parses a value with fewer than three dots as a NUMBER, so an "
            "address typed one octet short arrives here as a float rather "
            "than as the address you meant.",
            code=ErrorCode.VALIDATION,
            remediation=(
                f'Quote it: `requested_address: "192.168.11.174"` for the '
                f"{name!r} entry."
            ),
        )
    address = raw.strip()
    if not address:
        raise HostRegistryError(
            f"{hosts_path}: host {name!r}: `requested_address` is empty. An "
            "empty string cannot be told apart from 'no preference', which "
            "is what omitting the field already says.",
            code=ErrorCode.VALIDATION,
            remediation=(
                f"Either give {name!r} a real address or delete the "
                "`requested_address:` line."
            ),
        )
    return address


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
            requested_address=_parse_requested_address(
                name, data.get("requested_address"), hosts_path=hosts_path
            ),
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
