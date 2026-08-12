#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Three independent signals, and the rule that an address is only rewritten
when all three agree.

This encodes the manual procedure that made the 2026-08-13 address rewrite
safe, so the next one does not depend on somebody remembering it.

THE SIGNALS, WEAKEST TO STRONGEST
----------------------------------
1. **MAC** (:data:`SIGNAL_MAC`) — the router reserves a MAC at an address and
   the registry records that MAC. The NIC answering at the proposed address
   is read from the neighbour/ARP table and compared. Agreement means the
   address is INTENDED for this machine.

2. **SSH host-key continuity** (:data:`SIGNAL_HOST_KEY`) — the strongest, and
   the one that actually settled it on the day. A machine that moves keeps
   its host key, so ssh itself says ``This host key is known by the following
   other names/addresses: ... 192.168.11.161``. That is positive proof of
   "the SAME machine, readdressed", which no amount of successful connecting
   can establish on its own: a different box answering at the old address
   also connects fine.

3. **Live probe** (:data:`SIGNAL_PROBE`) — connect and read back ``hostname``.
   The machine's own claim about who it is.

They are independent on purpose: MAC comes from the router's view, the host
key from the machine's persistent identity, the hostname from its running
configuration. A fault that fools one rarely fools the other two.

THE RULE
--------
* all three AVAILABLE and AGREEING -> :data:`VERDICT_CORROBORATED`, and the
  generator may rewrite the address automatically;
* any available signal DISAGREEING -> :data:`VERDICT_CONFLICT`. Do not
  rewrite. Record it and escalate to a human. A machine can DETECT
  disagreement; it cannot decide which source is telling the truth, and
  picking a winner silently is how a wrong address gets baked in and then
  propagated to every host by the generator;
* fewer than three signals available -> :data:`VERDICT_INSUFFICIENT`, which
  is NOT a pass. **"No contradiction found" is not "corroborated."** That
  conflation — a success value that is also the didn't-check value — is the
  single most repeated defect in this fleet's tooling, so the verdict here
  is computed from the count of signals that ACTUALLY RAN, and the missing
  ones are named in the output.

WHERE THE GATE SITS, AND WHAT IS NOT HERE YET
----------------------------------------------
:attr:`Corroboration.may_rewrite` is the DECISION; the automatic rewriter
that would consume it is deliberately NOT in this module. Writing an address
back means rewriting ``hosts.yaml``, and that file is roughly two-thirds
COMMENTS carrying the fleet's operational memory — why a NAS is keyed the way
it is, which retired alias maps where, what a runner label costs. A
round-trip through a YAML emitter deletes all of it silently, which is a
worse outcome than a manual edit. (It would also have to satisfy
:func:`~._write_target.resolve_hosts_yaml_for_write`, which refuses outright
from inside an agent container.)

So the enforcement today is the CLI contract: ``scitex-dev host corroborate``
exits ``0`` only when :attr:`~Corroboration.may_rewrite` is true, ``2`` on a
conflict and ``1`` on insufficient evidence. Anything that edits an address
runs it first and honours the exit code; a comment-preserving writer is the
follow-up that makes that automatic.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from ._connectivity import normalize_fingerprint, normalize_mac
from ._run import run_command, ssh_base_argv

__all__ = [
    "Corroboration",
    "REQUIRED_SIGNALS",
    "SIGNAL_HOST_KEY",
    "SIGNAL_MAC",
    "SIGNAL_PROBE",
    "Signal",
    "VERDICT_CONFLICT",
    "VERDICT_CORROBORATED",
    "VERDICT_INSUFFICIENT",
    "corroborate",
]

SIGNAL_MAC = "mac-reservation"
SIGNAL_HOST_KEY = "host-key-continuity"
SIGNAL_PROBE = "live-hostname"

#: All three are REQUIRED for a rewrite. Two agreeing signals are two
#: signals, not a consensus.
REQUIRED_SIGNALS = (SIGNAL_MAC, SIGNAL_HOST_KEY, SIGNAL_PROBE)

VERDICT_CORROBORATED = "corroborated"
VERDICT_CONFLICT = "conflict"
VERDICT_INSUFFICIENT = "insufficient"

_MAC_RE_HINT = "aa:bb:cc:dd:ee:ff"


@dataclass(frozen=True)
class Signal:
    """One signal's outcome.

    ``agrees`` is a THREE-valued field — ``True`` / ``False`` / ``None`` for
    "could not tell". Collapsing ``None`` into ``False`` would report an
    absent tool as a conflict and block every rewrite; collapsing it into
    ``True`` would report it as corroboration and permit every rewrite. Both
    are wrong, so the third value is kept and the verdict reads it.
    """

    name: str
    available: bool
    agrees: bool | None
    expected: str | None
    observed: str | None
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "available": self.available,
            "agrees": self.agrees,
            "expected": self.expected,
            "observed": self.observed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Corroboration:
    """The verdict on one proposed address, with its evidence."""

    host: str
    proposed_address: str
    signals: tuple[Signal, ...]
    notes: tuple[str, ...] = ()

    @property
    def available(self) -> tuple[Signal, ...]:
        return tuple(s for s in self.signals if s.available)

    @property
    def disagreeing(self) -> tuple[Signal, ...]:
        return tuple(s for s in self.signals if s.agrees is False)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.signals if not s.available)

    @property
    def verdict(self) -> str:
        if self.disagreeing:
            return VERDICT_CONFLICT
        if len(self.available) < len(REQUIRED_SIGNALS):
            return VERDICT_INSUFFICIENT
        return VERDICT_CORROBORATED

    @property
    def may_rewrite(self) -> bool:
        """The single boolean a caller is allowed to act on."""
        return self.verdict == VERDICT_CORROBORATED

    def summary_line(self) -> str:
        agreeing = sum(1 for s in self.available if s.agrees)
        line = (
            f"{self.verdict}: {agreeing}/{len(REQUIRED_SIGNALS)} signals agree "
            f"for {self.host} at {self.proposed_address} "
            f"({len(self.available)} of {len(REQUIRED_SIGNALS)} available)"
        )
        if self.missing:
            line += f"; NOT CHECKED: {', '.join(self.missing)}"
        return line

    def escalation(self) -> str | None:
        """What a human is being asked to decide, or ``None`` if nothing."""
        if self.verdict == VERDICT_CONFLICT:
            conflicts = "; ".join(
                f"{s.name}: expected {s.expected!r}, observed {s.observed!r}"
                for s in self.disagreeing
            )
            return (
                f"CONFLICT for {self.host} at {self.proposed_address} — "
                f"{conflicts}. NOT rewriting. Two sources disagree about which "
                "machine is at this address; deciding which one is right is a "
                "human judgement, and guessing it writes a wrong address into "
                "every host's ssh config at once."
            )
        if self.verdict == VERDICT_INSUFFICIENT:
            return (
                f"INSUFFICIENT evidence for {self.host} at "
                f"{self.proposed_address} — {', '.join(self.missing)} could "
                "not be checked. Nothing contradicted the address, which is "
                "NOT the same as corroborating it."
            )
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "proposed_address": self.proposed_address,
            "verdict": self.verdict,
            "may_rewrite": self.may_rewrite,
            "required_signals": list(REQUIRED_SIGNALS),
            "available": len(self.available),
            "missing": list(self.missing),
            "summary": self.summary_line(),
            "escalation": self.escalation(),
            "notes": list(self.notes),
            "signals": [s.to_dict() for s in self.signals],
        }


def _unavailable(name: str, expected: str | None, detail: str) -> Signal:
    return Signal(name, False, None, expected, None, detail)


def observe_mac(address: str, *, runner=run_command, timeout: float = 5.0) -> str | None:
    """The MAC currently answering at ``address``, or ``None``.

    Tries ``ip neigh`` then ``arp -n``. ``None`` when neither tool is
    installed OR the address has no neighbour entry — both are genuinely
    "we do not know", and the caller reports them as an UNAVAILABLE signal
    rather than as a mismatch. (Neither binary exists inside the fleet's
    agent containers, so this is the ordinary case there, not an edge one.)
    """
    for argv in (["ip", "neigh", "show", address], ["arp", "-n", address]):
        result = runner(argv, timeout=timeout)
        if not result.ok:
            continue
        for token in result.stdout.replace("\n", " ").split():
            candidate = token.strip().lower().replace("-", ":")
            if candidate.count(":") == 5 and len(candidate) == 17:
                try:
                    return normalize_mac("<observed>", candidate)
                except Exception:  # pragma: no cover - regex already matched
                    continue
    return None


def observe_host_keys(
    address: str, *, runner=run_command, timeout: float = 10.0
) -> tuple[str, ...]:
    """Fingerprints of the ssh host keys served at ``address``.

    ``ssh-keyscan`` reads PUBLIC keys only — that is the whole point of the
    signal, and it is why this comparison can be shipped: a host key
    fingerprint is a public identity, not a secret.
    """
    scan = runner(["ssh-keyscan", "-T", str(int(timeout)), address], timeout=timeout)
    if not scan.stdout.strip():
        return ()
    with tempfile.TemporaryDirectory() as tmp:
        keyfile = Path(tmp) / "known"
        keyfile.write_text(scan.stdout)
        listed = runner(["ssh-keygen", "-lf", str(keyfile)], timeout=timeout)
    out = []
    for line in listed.stdout.splitlines():
        fingerprint = normalize_fingerprint(line)
        if fingerprint:
            out.append(fingerprint)
    return tuple(out)


def observe_hostname(
    address: str, *, runner=run_command, timeout: float = 15.0, connect_timeout: int = 5
) -> str | None:
    """What the machine at ``address`` calls itself, or ``None``."""
    argv = ssh_base_argv(connect_timeout=connect_timeout) + [address, "hostname"]
    result = runner(argv, timeout=timeout)
    if not result.ok:
        return None
    value = result.stdout.strip().splitlines()
    return value[0].strip() if value else None


def _mac_signal(record, address: str, *, runner, timeout) -> Signal:
    expected = record.connectivity.mac
    if not expected:
        return _unavailable(
            SIGNAL_MAC,
            None,
            "the registry records no `mac:` for this host, so there is "
            f"nothing to compare against (write it as `mac: {_MAC_RE_HINT}`).",
        )
    observed = observe_mac(address, runner=runner, timeout=timeout)
    if observed is None:
        return _unavailable(
            SIGNAL_MAC,
            expected,
            f"no neighbour entry for {address}, or neither `ip` nor `arp` is "
            "installed here. NOT a mismatch — simply unknown.",
        )
    agrees = observed == expected
    return Signal(
        SIGNAL_MAC,
        True,
        agrees,
        expected,
        observed,
        "the NIC answering at this address is the one the registry records"
        if agrees
        else "a DIFFERENT NIC is answering at this address",
    )


def _host_key_signal(record, address: str, *, runner, timeout) -> Signal:
    expected = record.connectivity.host_key_fingerprint
    if not expected:
        return _unavailable(
            SIGNAL_HOST_KEY,
            None,
            "the registry records no `host_key_fingerprint:`, so continuity "
            "cannot be established. This is the strongest of the three "
            "signals; recording it is the highest-value thing to add.",
        )
    observed = observe_host_keys(address, runner=runner, timeout=timeout)
    if not observed:
        return _unavailable(
            SIGNAL_HOST_KEY,
            expected,
            f"nothing served an ssh host key at {address} (host down, port "
            "filtered, or ssh-keyscan unavailable).",
        )
    agrees = expected in observed
    return Signal(
        SIGNAL_HOST_KEY,
        True,
        agrees,
        expected,
        ", ".join(observed),
        "same host key — positive proof this is the SAME machine, readdressed"
        if agrees
        else "the host key at this address is NOT this machine's recorded key",
    )


def _probe_signal(record, address: str, *, runner, timeout, connect_timeout) -> Signal:
    expected = record.connectivity.reported_hostname
    if not expected:
        return _unavailable(
            SIGNAL_PROBE,
            None,
            "the registry records no `reported_hostname:`. The registry KEY is "
            "not a substitute — the NAS boxes are keyed `scitex-nas-01` and "
            "call themselves `WATANAS1`, so comparing against the key would "
            "manufacture a conflict.",
        )
    observed = observe_hostname(
        address, runner=runner, timeout=timeout, connect_timeout=connect_timeout
    )
    if observed is None:
        return _unavailable(
            SIGNAL_PROBE,
            expected,
            f"could not connect to {address} to ask. Unreachable is not "
            "evidence either way.",
        )
    agrees = observed.strip().lower() == expected.strip().lower()
    return Signal(
        SIGNAL_PROBE,
        True,
        agrees,
        expected,
        observed,
        "the machine agrees about its own name"
        if agrees
        else "the machine at this address calls itself something else",
    )


def corroborate(
    record,
    address: str | None = None,
    *,
    runner=run_command,
    timeout: float = 15.0,
    connect_timeout: int = 5,
) -> Corroboration:
    """Run all three signals against ``address`` and return the verdict.

    ``address`` defaults to the record's OBSERVED ``lan``. Pass the
    reservation explicitly to ask the other question — "is the machine
    reachable where it is supposed to be?" — which is a different question
    with a different answer whenever a lease has not renewed.

    Always runs every signal, even after one disagrees: the point of an
    escalation is to hand a human the whole picture, and stopping at the
    first mismatch would hide whether the other two back it up.
    """
    conn = record.connectivity
    target = address or conn.lan
    if not target:
        # Every signal unavailable -> `insufficient`, never `corroborated`.
        # A host with no address recorded is the case most likely to be read
        # as "nothing wrong here", so it must produce the same loud
        # not-checked verdict as a host whose probes all failed.
        return Corroboration(
            record.name,
            "",
            tuple(
                _unavailable(name, None, "no address to check")
                for name in REQUIRED_SIGNALS
            ),
            notes=("the registry records no `lan:` address for this host",),
        )

    signals = (
        _mac_signal(record, target, runner=runner, timeout=timeout),
        _host_key_signal(record, target, runner=runner, timeout=timeout),
        _probe_signal(
            record,
            target,
            runner=runner,
            timeout=timeout,
            connect_timeout=connect_timeout,
        ),
    )

    notes: list[str] = []
    matches = conn.reservation_matches_observed
    if matches is False:
        notes.append(
            f"reserved {conn.reserved} != observed {conn.lan} — the DHCP "
            "reservation exists but the lease has not renewed. Both are true; "
            "neither is a conflict by itself."
        )
    elif matches is None and (conn.reserved or conn.lan):
        notes.append(
            "only one of `reserved`/`lan` is recorded, so the intended and "
            "actual addresses cannot be compared."
        )
    return Corroboration(record.name, target, signals, tuple(notes))


# EOF
