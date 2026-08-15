#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The transport that actually crossed the wire: ssh, then ``pg_notify``.

Verified end-to-end 2026-08-15, ``scitex-compute-04`` -> ``ywata-note-win``:
three hints sent, three received on the laptop's channel, in order, payloads
identical. See :mod:`._relay` for why the fan-out is shaped this way and for
the measurements (loopback-only Postgres, 5x multiplexing win) behind it.

WHY ``psql -v`` AND NOT AN f-STRING
------------------------------------
The payload is interpolated into SQL on the far side, so the obvious
``f"select pg_notify('{channel}', '{payload}')"`` is an injection site. It is a
small one — :func:`~._notify.encode_hint` already refuses ``:`` and bounds the
length, and origins are hostnames — but "the input happens to be tame today"
is not a defence that survives someone widening the payload later.

``psql`` has the right tool: ``-v name=value`` binds a variable, and
``:'name'`` interpolates it AS A PROPERLY QUOTED LITERAL. A quote in the value
becomes a quoted quote rather than the end of the string.

Both hops are covered, because there are two:

* the SQL hop, by ``:'var'``;
* the SHELL hop — the argv is reassembled by the peer's login shell — by
  :func:`shlex.quote`.

Fixing only the first would leave a value like ``x; rm -rf ~`` to the remote
shell, so the argv builder is one pure function and it is tested directly.
"""

from __future__ import annotations

import shlex
import subprocess
from typing import Final, Sequence

from ._relay import TransportError

#: Ring the peer's Postgres over its OWN loopback, with its OWN credentials.
#: Never the peer's LAN address: the operator's laptop binds 127.0.0.1 only,
#: measured 2026-08-15, so a routable address would fail for the single
#: destination this whole path exists to serve.
_PEER_HOST: Final[str] = "127.0.0.1"

#: Keep the connection warm. Measured on the compute-04 -> laptop pair:
#: 425-485 ms per ring cold, 79-91 ms multiplexed. A hint is a latency
#: optimisation, so a transport that spends 400 ms on key exchange has spent
#: the thing it was buying.
_MUX_OPTS: Final[tuple[str, ...]] = (
    "-o",
    "BatchMode=yes",
    "-o",
    "ControlMaster=auto",
    "-o",
    "ControlPath=~/.ssh/cm-scitex-relay-%r@%h:%p",
    "-o",
    "ControlPersist=300",
)

#: Bound EVERY ring. Without it one hung peer stalls the fan-out behind it,
#: and the symptom is the fleet's favourite failure: nothing arrives, nothing
#: errors. 10 s is ~20x the measured cold-connect cost.
_DEFAULT_TIMEOUT_S: Final[float] = 10.0

_REMOTE_SQL: Final[str] = "select pg_notify(:'chan', :'payload')"


def ring_argv(
    ssh_alias: str,
    channel: str,
    payload: str,
    *,
    port: int = 55432,
    user: str = "scitex_cards",
    dbname: str = "scitex_cards",
    connect_timeout: int = 5,
) -> list[str]:
    """Build the argv that rings ONE peer. Pure — no process is started.

    Split out from :class:`SshPsqlTransport` so the two quoting hops can be
    asserted directly. A transport whose only test is "it worked against the
    laptop" proves the happy path and nothing about a hostile payload.
    """
    if not ssh_alias:
        raise ValueError("ssh_alias must be a non-empty host alias")
    remote = " ".join(
        [
            "psql",
            "-h",
            _PEER_HOST,
            "-p",
            str(port),
            "-U",
            shlex.quote(user),
            "-d",
            shlex.quote(dbname),
            "-w",  # never prompt: a relay has no terminal to answer on
            "-tAq",
            "-v",
            shlex.quote(f"chan={channel}"),
            "-v",
            shlex.quote(f"payload={payload}"),
            "-c",
            shlex.quote(_REMOTE_SQL),
        ]
    )
    return [
        "ssh",
        *_MUX_OPTS,
        "-o",
        f"ConnectTimeout={connect_timeout}",
        ssh_alias,
        remote,
    ]


class SshPsqlTransport:
    """Ring a peer by running ``pg_notify`` inside the peer's own database.

    ``aliases`` maps a peer NAME to its ssh alias. It is passed in rather than
    read from the host registry on purpose: on 2026-08-15 the registry recorded
    ``ywata-note-win`` with no ssh alias while ssh to it worked in both
    directions, so a transport that trusted the registry would have silently
    dropped the operator's laptop — the exact destination he asked for. A peer
    with no alias here raises; it is never skipped.
    """

    def __init__(
        self,
        aliases: dict[str, str],
        *,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        runner: object | None = None,
        **psql: object,
    ) -> None:
        self._aliases = dict(aliases)
        self._timeout_s = timeout_s
        self._psql = psql
        # `runner` exists so a caller can supply a real alternative launcher
        # (a sudo wrapper, a jump-host helper). Defaults to subprocess.run.
        self._run = runner or subprocess.run

    def deliver(self, peer: str, channel: str, payload: str) -> None:
        alias = self._aliases.get(peer)
        if not alias:
            raise TransportError(
                f"no ssh alias declared for peer {peer!r} — refusing to treat "
                "an unroutable peer as a delivered one"
            )
        argv = ring_argv(alias, channel, payload, **self._psql)  # type: ignore[arg-type]
        try:
            proc = self._run(
                argv, capture_output=True, text=True, timeout=self._timeout_s
            )
        except subprocess.TimeoutExpired as exc:
            raise TransportError(
                f"{peer}: ring timed out after {self._timeout_s}s"
            ) from exc
        except OSError as exc:
            raise TransportError(f"{peer}: could not launch ssh — {exc}") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise TransportError(
                f"{peer}: ring exited {proc.returncode}"
                + (f" — {detail[-1]}" if detail else "")
            )


def aliases_for(peers: Sequence[str]) -> dict[str, str]:
    """Identity mapping, for the common case where a peer name IS its alias.

    Provided so a caller does not hand-write ``{p: p for p in peers}`` and
    quietly disagree with the next caller about whether a missing entry means
    "same name" or "unreachable". Here it means SAME NAME, and an absent peer
    still raises in :meth:`SshPsqlTransport.deliver`.
    """
    return {peer: peer for peer in peers}


# EOF
