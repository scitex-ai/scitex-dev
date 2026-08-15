#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reachability across ORDERED pairs — and the denominator, always.

A mesh is not "can I reach everything". It is N*(N-1) ordered pairs per
transport, and A->B succeeding says nothing about B->A: they use different
keys, different authorized_keys files, and often different routes.

WHY THE DENOMINATOR IS PART OF THE RESULT TYPE
-----------------------------------------------
A bare "12 passed" cannot be distinguished from "12 passed and 30 were never
attempted", and the second is the ordinary outcome of a sweep that lost its
ssh agent halfway through. :class:`MatrixResult` therefore carries
:attr:`~MatrixResult.expected` (what a complete sweep WOULD be),
:attr:`~MatrixResult.attempted` (what was really tried) and the skips with
their reasons, and :attr:`~MatrixResult.verdict` is ``"pass"`` ONLY when
those two agree and nothing failed. A sweep that could not run reports
``"incomplete"``, never ``"pass"``.

This is the same trap as a check whose success value is also its
didn't-check value. Here the pass count is the tempting single number, and
it is exactly the one that cannot tell the two apart.
"""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ._connectivity import net_name
from ._run import CommandResult, run_command, ssh_base_argv

__all__ = [
    "MatrixResult",
    "PairProbe",
    "STATUS_FAILED",
    "STATUS_OK",
    "STATUS_SKIPPED",
    "check_matrix",
    "local_host_name",
]

STATUS_OK = "ok"
STATUS_FAILED = "failed"
#: NOT a pass. A skip means the probe never ran, and the reason is carried
#: with it so a reader can tell "no route recorded" from "no way to get to
#: the source host" — different problems with different fixes.
STATUS_SKIPPED = "skipped"

#: The transports a sweep can walk. ``lan`` uses the bare canonical name,
#: ``net`` uses ``<name>-net``. They are separate sweeps because a host can
#: be perfectly reachable on one and dead on the other, and averaging them
#: would hide whichever is broken.
DEFAULT_TRANSPORTS = ("lan", "net")


@dataclass(frozen=True)
class PairProbe:
    """One ordered (source -> target) attempt over one transport."""

    source: str
    target: str
    transport: str
    alias: str | None
    status: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "transport": self.transport,
            "alias": self.alias,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class MatrixResult:
    """Every probe, plus the denominator that makes the counts readable."""

    hosts: tuple[str, ...]
    transports: tuple[str, ...]
    probes: tuple[PairProbe, ...]

    @property
    def expected(self) -> int:
        """N*(N-1) ordered pairs per transport — a COMPLETE sweep's size."""
        n = len(self.hosts)
        return n * (n - 1) * len(self.transports)

    @property
    def ok(self) -> int:
        return sum(1 for p in self.probes if p.status == STATUS_OK)

    @property
    def failed(self) -> int:
        return sum(1 for p in self.probes if p.status == STATUS_FAILED)

    @property
    def skipped(self) -> int:
        return sum(1 for p in self.probes if p.status == STATUS_SKIPPED)

    @property
    def attempted(self) -> int:
        """Probes that actually ran. Skips are NOT attempts."""
        return self.ok + self.failed

    @property
    def complete(self) -> bool:
        return self.attempted == self.expected

    @property
    def verdict(self) -> str:
        """``pass`` / ``fail`` / ``incomplete``.

        ``pass`` requires BOTH that nothing failed AND that the sweep was
        complete. A sweep with 40 skips and 2 passes is ``incomplete``, and
        calling it anything else would be the report telling the operator
        the mesh is healthy on the strength of two measurements.
        """
        if self.failed:
            return "fail"
        return "pass" if self.complete else "incomplete"

    def summary_line(self) -> str:
        """One line that can never be read as a bare pass count."""
        return (
            f"{self.verdict}: {self.ok} ok / {self.attempted} attempted "
            f"of {self.expected} ordered pairs "
            f"({len(self.hosts)} hosts x {len(self.transports)} transport(s)); "
            f"{self.failed} failed, {self.skipped} skipped"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "hosts": list(self.hosts),
            "transports": list(self.transports),
            "expected_ordered_pairs": self.expected,
            "attempted": self.attempted,
            "ok": self.ok,
            "failed": self.failed,
            "skipped": self.skipped,
            "complete": self.complete,
            "verdict": self.verdict,
            "summary": self.summary_line(),
            "probes": [p.to_dict() for p in self.probes],
        }


def local_host_name(records, *, hostname: str | None = None) -> str | None:
    """Which registry entry, if any, is THIS machine.

    Matched against the canonical name, the aliases, and the recorded
    ``reported_hostname`` — the NAS boxes call themselves ``WATANAS1`` while
    the registry keys them ``scitex-nas-01``, so name equality alone would
    answer ``None`` on the very machines that have the field.

    ``None`` means "this machine is not in the registry", which is the
    correct answer inside an agent container and makes every source host
    require an ssh hop. That is slower and it is honest; assuming the
    container is one of the fleet's machines would attribute its results to
    a host that never ran them.
    """
    me = (hostname or socket.gethostname()).strip().lower()
    for record in records:
        candidates = {record.name.lower()}
        candidates.update(a.lower() for a in record.aliases)
        if record.connectivity.reported_hostname:
            candidates.add(record.connectivity.reported_hostname.lower())
        if me in candidates or me.split(".")[0] in candidates:
            return record.name
    return None


def _target_alias(record, transport: str) -> str | None:
    """The ssh name for ``record`` over ``transport``, or None if unrecorded."""
    if transport == "lan":
        return record.name if record.connectivity.lan else None
    if transport == "net":
        return net_name(record.name) if record.connectivity.net else None
    return None


def _probe_argv(
    source, target_alias: str, *, is_local: bool, connect_timeout: int
) -> list[str]:
    """Build the argv for one ordered probe.

    From the LOCAL machine it is a plain ``ssh <target> true``. From any
    other source it is that command run THROUGH the source
    (``ssh <source> ssh <target> true``), which is what makes the pair
    ORDERED — it measures the source's own keys and config, not ours.
    """
    inner = ssh_base_argv(connect_timeout=connect_timeout) + [target_alias, "true"]
    if is_local:
        return inner
    hop = source.ssh_alias or source.name
    return ssh_base_argv(connect_timeout=connect_timeout) + [hop, " ".join(inner)]


def _classify(result: CommandResult) -> tuple[str, str]:
    if result.ok:
        return STATUS_OK, "connected"
    if result.timed_out:
        return STATUS_FAILED, "timed out"
    if result.transport_failed:
        return STATUS_FAILED, f"ssh could not connect: {result.first_error_line()}"
    return STATUS_FAILED, result.first_error_line()


def check_matrix(
    records,
    *,
    transports=DEFAULT_TRANSPORTS,
    runner=run_command,
    hostname: str | None = None,
    connect_timeout: int = 5,
    timeout: float = 20.0,
    max_workers: int = 8,
) -> MatrixResult:
    """Probe every ORDERED pair over every transport.

    Skips — which are reported, never silently dropped — happen when:

    * the TARGET records no address for that transport (most machines are
      LAN-only, so the ``net`` sweep is mostly skips and the report must say
      so rather than showing a small green number);
    * the SOURCE is neither this machine nor reachable by an ssh alias, so
      there is no way to run anything from it.

    Probes run concurrently because a complete sweep is N*(N-1) per
    transport and a serial walk of a 7-host fleet at a 20s ceiling is
    twenty-eight minutes — long enough that in practice it gets interrupted,
    which produces exactly the partial result this module refuses to call a
    pass.
    """
    records = list(records)
    transports = tuple(transports)
    me = local_host_name(records, hostname=hostname)

    jobs: list[tuple[PairProbe, list[str] | None]] = []
    for source in records:
        for target in records:
            if source.name == target.name:
                continue
            for transport in transports:
                alias = _target_alias(target, transport)
                if alias is None:
                    jobs.append(
                        (
                            PairProbe(
                                source.name,
                                target.name,
                                transport,
                                None,
                                STATUS_SKIPPED,
                                f"target records no `{transport}` route",
                            ),
                            None,
                        )
                    )
                    continue
                is_local = source.name == me
                if not is_local and not source.ssh_alias:
                    jobs.append(
                        (
                            PairProbe(
                                source.name,
                                target.name,
                                transport,
                                alias,
                                STATUS_SKIPPED,
                                "source has no ssh_alias and is not this "
                                "machine — nothing can be run from it",
                            ),
                            None,
                        )
                    )
                    continue
                jobs.append(
                    (
                        PairProbe(
                            source.name, target.name, transport, alias, "", ""
                        ),
                        _probe_argv(
                            source,
                            alias,
                            is_local=is_local,
                            connect_timeout=connect_timeout,
                        ),
                    )
                )

    runnable = [(i, argv) for i, (_, argv) in enumerate(jobs) if argv is not None]
    outcomes: dict[int, CommandResult] = {}
    if runnable:
        workers = max(1, min(max_workers, len(runnable)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(runner, argv, timeout=timeout): i for i, argv in runnable
            }
            for future, index in futures.items():
                outcomes[index] = future.result()

    probes: list[PairProbe] = []
    for index, (probe, argv) in enumerate(jobs):
        if argv is None:
            probes.append(probe)
            continue
        status, detail = _classify(outcomes[index])
        probes.append(
            PairProbe(
                probe.source, probe.target, probe.transport, probe.alias, status, detail
            )
        )

    return MatrixResult(
        hosts=tuple(r.name for r in records),
        transports=transports,
        probes=tuple(probes),
    )


# EOF
