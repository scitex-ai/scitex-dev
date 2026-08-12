#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Connectivity state — HOW a machine is reached, and WHEN that was last true.

The registry already answered "where is host X's ``~/.scitex``". This module
adds the other half nobody could look up: the ADDRESS, the ROUTE, and the
identity facts that let a check decide whether an address still points at the
machine it used to.

THE NAMING RULE (operator ruling, 2026-08-13)
---------------------------------------------
The BARE canonical name is the LAN route. The ``-net`` suffix is ONLY for a
route that LEAVES the LAN (Cloudflare, reverse SSH). **A bare name never
carries a bastion route.**

This is enforced STRUCTURALLY rather than by a validator, which is why the
schema is shaped the way it is: the LAN side has no ``jump`` and no
``proxy_command`` field to put one in, and the off-LAN side lives in its own
:class:`NetRoute` that the generator can only ever emit under the ``-net``
name. A rule you cannot express is a rule that cannot rot into a comment
nobody reads — and a bastion route silently attached to a bare name is
exactly the fault that produced the 2026-08-13 mesh incident.

RESERVED IS NOT OBSERVED
------------------------
:attr:`HostConnectivity.lan` (observed) and :attr:`HostConnectivity.reserved`
(the DHCP reservation) are SEPARATE FIELDS on purpose, and collapsing them
would erase a live fact. Measured 2026-08-13: scitex-compute-01 is reserved
at ``192.168.11.171`` and answering at ``192.168.11.94`` because the lease has
not been renewed. Both statements are true. A registry with one address field
must either lie about where the machine is, or lie about where it is supposed
to be.

NO PRIVATE KEY MATERIAL, EVER
-----------------------------
Only PUBLIC facts are state here: an address, a MAC, a host-key FINGERPRINT,
the PATH of an identity file. :func:`reject_key_material` is a hard guard on
the parse path — a value carrying a PEM header, or a field named as though it
holds a secret, raises instead of being stored. Private keys never leave the
machine that generated them, so they are never registry state, and a field
that could hold one must not exist to be filled in by accident.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .._core.errors import ErrorCode

__all__ = [
    "NET_SUFFIX",
    "TRANSPORTS",
    "HostConnectivity",
    "NetRoute",
    "net_name",
    "normalize_fingerprint",
    "normalize_mac",
    "reject_key_material",
]

#: Suffix for the OFF-LAN alias. See the module docstring — this suffix, and
#: only this suffix, may carry a bastion/jump route.
NET_SUFFIX = "-net"

#: Closed set of off-LAN transports. Closed because the ssh-config generator
#: branches on it: an unrecognised transport would render a stanza with no
#: proxy at all, i.e. a name that resolves and cannot connect.
TRANSPORTS: frozenset[str] = frozenset({"direct", "cloudflared", "reverse-ssh"})

#: Field names that could only ever hold a SECRET. Present as a deny-list
#: rather than an allow-list so an ordinary unknown key in someone's
#: hosts.yaml keeps parsing (the registry has always ignored extras) while
#: the one category that must never be written still fails loud.
FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "id_ed25519",
        "id_rsa",
        "key_material",
        "passphrase",
        "password",
        "private_key",
        "privatekey",
        "secret",
        "secret_key",
        "ssh_private_key",
    }
)

_PEM_MARKERS = ("-----BEGIN", "PRIVATE KEY")
_MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
_FINGERPRINT_RE = re.compile(r"\b((?:SHA256|MD5):[A-Za-z0-9+/=:]+)")


def net_name(name: str) -> str:
    """The OFF-LAN alias for ``name``. Idempotent.

    ``scitex-nas-03`` -> ``scitex-nas-03-net``, and a name that already
    carries the suffix is returned unchanged so a caller cannot produce
    ``...-net-net`` by asking twice.
    """
    return name if name.endswith(NET_SUFFIX) else f"{name}{NET_SUFFIX}"


def reject_key_material(host: str, data, *, where: str) -> None:
    """Raise if ``data`` names or carries private key material.

    Two independent checks, because they catch different accidents:

    * a FIELD NAME from :data:`FORBIDDEN_FIELDS` — someone reaching for a
      place to put a key and finding the registry;
    * a PEM header in any string VALUE — someone pasting one into a field
      that was innocent, e.g. ``note:``.

    The registry is synced, committed and read by every host in the fleet.
    A secret that reaches it is disclosed to all of them at once and cannot
    be recalled, so this fails at PARSE time rather than at use time.
    """
    from ._registry import HostRegistryError

    if isinstance(data, dict):
        for key in data:
            if str(key).strip().lower() in FORBIDDEN_FIELDS:
                raise HostRegistryError(
                    f"host {host!r}: field {key!r} in {where} is refused. The "
                    "host registry stores only PUBLIC connectivity facts — an "
                    "address, a MAC, a host-key FINGERPRINT, the PATH of an "
                    "identity file. Private key material never leaves the "
                    "machine that generated it, and this file is read by "
                    "every host in the fleet.",
                    code=ErrorCode.VALIDATION,
                    remediation=(
                        f"Delete {key!r}. If you meant the PATH of a key, use "
                        "`identity_file:` — a path is not key material."
                    ),
                )
        values = list(data.values())
    else:
        values = [data]

    for value in values:
        text = value if isinstance(value, str) else ""
        if any(marker in text for marker in _PEM_MARKERS):
            raise HostRegistryError(
                f"host {host!r}: a value in {where} contains a PEM key header. "
                "Refusing to store key material in the host registry.",
                code=ErrorCode.VALIDATION,
                remediation=(
                    "Remove the key from hosts.yaml. Record the PUBLIC "
                    "fingerprint under `host_key_fingerprint:` instead — that "
                    "is the field the corroboration check reads."
                ),
            )


def normalize_mac(host: str, raw) -> str | None:
    """Lowercase, colon-separated MAC, or ``None`` when absent.

    Normalised on the way IN so that a comparison later is a string equality
    and never a formatting question. ``24:5E:BE:00:CA:30`` and
    ``24:5e:be:00:ca:30`` are the same NIC; a corroboration check that
    reported them as disagreeing would block a rewrite that should proceed,
    which is the failure mode that erodes trust in the check itself.
    """
    from ._registry import HostRegistryError

    if raw is None:
        return None
    text = str(raw).strip().lower().replace("-", ":")
    if not _MAC_RE.match(text):
        raise HostRegistryError(
            f"host {host!r}: `mac` must be six colon-separated hex octets, "
            f"got {raw!r}",
            code=ErrorCode.VALIDATION,
            remediation="Write it as e.g. `mac: 70:85:c2:3a:a9:42`.",
        )
    return text


def normalize_fingerprint(raw) -> str | None:
    """Extract the ``SHA256:...`` token from a fingerprint string.

    Accepts a bare token or a full ``ssh-keygen -l`` line
    (``256 SHA256:xxxx user@host (ED25519)``) so the value recorded in the
    registry and the value read back off the wire compare directly. Returns
    ``None`` when nothing fingerprint-shaped is present — the caller reports
    that as an UNAVAILABLE signal, never as agreement.
    """
    if raw is None:
        return None
    match = _FINGERPRINT_RE.search(str(raw))
    return match.group(1) if match else None


@dataclass(frozen=True)
class NetRoute:
    """The route that LEAVES the LAN — rendered ONLY under ``<name>-net``.

    Attributes
    ----------
    transport : str
        One of :data:`TRANSPORTS`. ``cloudflared`` reaches the host through
        a Cloudflare Access tunnel; ``reverse-ssh`` hops through
        :attr:`jump`; ``direct`` is a reachable public address.
    hostname : str | None
        The address/name to hand ssh for this route (e.g.
        ``bastion.scitex.ai``). Distinct from the LAN address by
        construction — that separation IS the naming rule.
    port : int | None
        Non-default port, or ``None``.
    jump : str | None
        ``ProxyJump`` alias for ``reverse-ssh``.
    proxy_command : str | None
        Explicit ``ProxyCommand`` override. When ``None`` and the transport
        is ``cloudflared``, the generator emits the standard
        ``cloudflared access ssh --hostname %h``.
    """

    transport: str
    hostname: str | None = None
    port: int | None = None
    jump: str | None = None
    proxy_command: str | None = None

    def __post_init__(self) -> None:
        from ._registry import HostRegistryError

        if self.transport not in TRANSPORTS:
            raise HostRegistryError(
                f"unknown net transport {self.transport!r} "
                f"(must be one of: {', '.join(sorted(TRANSPORTS))})",
                code=ErrorCode.VALIDATION,
                remediation=(
                    "An unrecognised transport renders a stanza with no proxy "
                    "at all — a name that resolves and cannot connect. Pick a "
                    "known transport, or add one deliberately to TRANSPORTS "
                    "and teach the generator to render it."
                ),
            )
        if self.transport == "reverse-ssh" and not self.jump:
            raise HostRegistryError(
                "net transport 'reverse-ssh' requires `jump:` — without it "
                "the stanza has nothing to hop through.",
                code=ErrorCode.VALIDATION,
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "transport": self.transport,
            "hostname": self.hostname,
            "port": self.port,
            "jump": self.jump,
            "proxy_command": self.proxy_command,
        }


@dataclass(frozen=True)
class HostConnectivity:
    """Everything about REACHING a host, and how fresh that knowledge is.

    Every field is OPTIONAL. An existing ``hosts.yaml`` written before this
    module existed parses unchanged and yields an all-empty record — that is
    the compatibility contract, and :meth:`is_empty` is how a caller tells
    "nothing recorded" from "recorded as absent".

    Attributes
    ----------
    lan : str | None
        The OBSERVED LAN address — where the machine actually answered.
        This is what the bare ``Host <name>`` stanza gets.
    reserved : str | None
        The DHCP RESERVATION — where the machine is SUPPOSED to answer.
        Deliberately separate from :attr:`lan`; see the module docstring.
    net : NetRoute | None
        The off-LAN route, rendered under ``<name>-net`` and nowhere else.
    mac : str | None
        Normalised NIC address. Corroboration signal 1.
    host_key_fingerprint : str | None
        The host's PUBLIC ssh host-key fingerprint (``SHA256:...``).
        Corroboration signal 2, and the strongest of the three: a machine
        that changes address keeps its host key, so a fingerprint match is
        positive proof of "same machine, new address" rather than "some
        other box now answers here".
    reported_hostname : str | None
        What ``hostname`` prints ON the machine (e.g. ``WATANAS1``), which
        is often NOT the registry key. Corroboration signal 3 compares
        against this.
    ssh_user, identity_file : str | None
        Rendered into the stanza. ``identity_file`` is a PATH — never key
        material — and the declared-vs-actual check exists because a stanza
        naming a key that is not there makes ssh offer NO key at all.
    last_seen : str | None
        ISO date/timestamp of the last successful observation. This is how
        an entry AGES. An unreachable host is never deleted from the
        registry (operator rule: unreachable != delete); its ``last_seen``
        simply stops advancing, which is a fact a reader can weigh.
    """

    lan: str | None = None
    reserved: str | None = None
    net: NetRoute | None = None
    mac: str | None = None
    host_key_fingerprint: str | None = None
    reported_hostname: str | None = None
    ssh_user: str | None = None
    identity_file: str | None = None
    last_seen: str | None = None

    def is_empty(self) -> bool:
        """True when NOTHING is recorded — an unmigrated or minimal entry."""
        return not any(
            (
                self.lan,
                self.reserved,
                self.net,
                self.mac,
                self.host_key_fingerprint,
                self.reported_hostname,
                self.ssh_user,
                self.identity_file,
                self.last_seen,
            )
        )

    @property
    def reservation_matches_observed(self) -> bool | None:
        """Whether the machine is answering at its reserved address.

        ``None`` when either fact is missing — NOT ``True``. "We did not
        record a reservation" and "the reservation is honoured" are
        different states, and only one of them is evidence.
        """
        if not self.reserved or not self.lan:
            return None
        return self.reserved == self.lan

    def to_dict(self) -> dict[str, object]:
        return {
            "lan": self.lan,
            "reserved": self.reserved,
            "net": self.net.to_dict() if self.net else None,
            "mac": self.mac,
            "host_key_fingerprint": self.host_key_fingerprint,
            "reported_hostname": self.reported_hostname,
            "ssh_user": self.ssh_user,
            "identity_file": self.identity_file,
            "last_seen": self.last_seen,
        }


# EOF
