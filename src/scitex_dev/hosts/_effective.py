#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DECLARED vs EFFECTIVE — what ssh actually obeys, and whether the key is there.

Two questions this module answers that reading a config file cannot:

**1. Does the stanza that WINS say what the registry says?** ssh takes the
FIRST value it obtains for each keyword and expands ``Include`` in place, so
the file a human opens is not necessarily the file ssh obeys. Measured
2026-08-13: ``~/.ssh/config`` line 1 was ``Include conf.d/*/*.conf``, an
included stanza silently beat every stanza below it, and the result was a
bastion route attached to a bare name plus two dead addresses — none of it
visible by reading the file people believed was in charge. ``ssh -G`` is the
only honest reader, because it is ssh answering about itself.

**2. Does the key the stanza NAMES actually exist here?** This was the single
real mesh failure of 2026-08-13. scitex-compute-01's stanza named
``~/.ssh/id_rsa``, which does not exist on that machine, so ssh offered NO
key at all and got ``Permission denied`` — while its ``id_mesh`` key was
already authorised at the far end. Every layer looked right: the stanza was
present and syntactically valid, the far end's ``authorized_keys`` was
correct, and the failure named neither.

Reading ssh — the argv, the parse, the built-in identity set — lives in
:mod:`._ssh_g`. This module owns the POLICY: what counts as declared, what
counts as a finding, and when a report may call itself a pass. The split
follows the ``_registry`` / ``_parse`` seam: that module changes when ssh
does, this one when the check's judgement does.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._connectivity import net_name
from ._run import run_command
from ._ssh_g import (
    builtin_identity_files,
    effective_config,
    identity_exists,
    parse_ssh_g,
)

__all__ = [
    "AliasCheck",
    "Finding",
    "SshConfigReport",
    "check_ssh_config",
    "effective_config",
    "parse_ssh_g",
]


@dataclass(frozen=True)
class Finding:
    """One problem, named so it can be counted and grepped."""

    host: str
    alias: str
    code: str
    severity: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "alias": self.alias,
            "code": self.code,
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AliasCheck:
    """What ssh resolves for one alias, and how that compares to the registry."""

    host: str
    alias: str
    checked: bool
    declared_hostname: str | None
    effective_hostname: str | None
    identity_files: tuple[str, ...]
    declared_identity_files: tuple[str, ...]
    missing_identity_files: tuple[str, ...]
    identities_only: bool
    findings: tuple[Finding, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "alias": self.alias,
            "checked": self.checked,
            "declared_hostname": self.declared_hostname,
            "effective_hostname": self.effective_hostname,
            "identity_files": list(self.identity_files),
            "declared_identity_files": list(self.declared_identity_files),
            "missing_identity_files": list(self.missing_identity_files),
            "identities_only": self.identities_only,
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass(frozen=True)
class SshConfigReport:
    """Every alias checked, with the denominator that makes zero readable."""

    on_host: str
    checks: tuple[AliasCheck, ...]
    #: Whether ssh's built-in identity set could be read. When ``False``,
    #: nothing can be classified as DECLARED, so a clean identity-file result
    #: means "could not tell" and the verdict must not be ``pass``.
    baseline_available: bool = True

    @property
    def expected(self) -> int:
        return len(self.checks)

    @property
    def checked(self) -> int:
        return sum(1 for c in self.checks if c.checked)

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(f for c in self.checks for f in c.findings)

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "error")

    @property
    def verdict(self) -> str:
        """``pass`` only when everything was checked AND nothing errored.

        An alias ``ssh -G`` refused to answer about is ``incomplete``, never
        a pass: "no finding" from a check that did not run is the same
        no-information the whole module exists to eliminate.
        """
        if self.errors:
            return "fail"
        if not self.baseline_available:
            return "incomplete"
        return "pass" if self.checked == self.expected else "incomplete"

    def summary_line(self) -> str:
        line = (
            f"{self.verdict}: {self.checked}/{self.expected} aliases resolved "
            f"on {self.on_host}; {len(self.errors)} error(s), "
            f"{len(self.findings) - len(self.errors)} warning(s)"
        )
        if not self.baseline_available:
            line += (
                "; ssh's built-in identity set could not be read, so NO key "
                "was classified as declared — identity findings are absent, "
                "not clean"
            )
        return line

    def to_dict(self) -> dict[str, object]:
        return {
            "on_host": self.on_host,
            "expected": self.expected,
            "checked": self.checked,
            "baseline_available": self.baseline_available,
            "verdict": self.verdict,
            "summary": self.summary_line(),
            "findings": [f.to_dict() for f in self.findings],
            "checks": [c.to_dict() for c in self.checks],
        }


def _check_alias(
    record,
    alias: str,
    declared_hostname: str | None,
    *,
    runner,
    config_file,
    hop,
    home: Path,
    builtin: tuple[str, ...],
    cache: dict,
    timeout: float,
    connect_timeout: int,
) -> AliasCheck:
    resolved = effective_config(
        alias,
        runner=runner,
        config_file=config_file,
        hop=hop,
        timeout=timeout,
        connect_timeout=connect_timeout,
    )
    if resolved is None:
        return AliasCheck(
            record.name, alias, False, declared_hostname, None, (), (), (), False,
            (
                Finding(
                    record.name,
                    alias,
                    "unresolved",
                    "warning",
                    "`ssh -G` did not answer for this alias, so nothing about "
                    "it was verified. This is NOT a pass.",
                ),
            ),
        )

    effective_hostname = (resolved.get("hostname") or [None])[0]
    identity_files = tuple(resolved.get("identityfile", []))
    # REPLACEMENT, not subtraction — see the module docstring. Subtracting the
    # defaults erases `~/.ssh/id_rsa`, which is exactly the file compute-01's
    # stanza named. When the baseline is unknown (empty) nothing is treated as
    # declared, and the report says the baseline was unavailable rather than
    # quietly reporting a clean result.
    declared = (
        () if (not builtin or identity_files == builtin) else identity_files
    )
    identities_only = (resolved.get("identitiesonly") or ["no"])[0].lower() == "yes"

    findings: list[Finding] = []
    if declared_hostname and effective_hostname != declared_hostname:
        findings.append(
            Finding(
                record.name,
                alias,
                "hostname-drift",
                "error",
                f"registry says {declared_hostname}, ssh resolves "
                f"{effective_hostname!r}. ssh obeys the FIRST stanza that "
                f"matches — check for an `Include` above the managed block.",
            )
        )

    def present(path: str) -> bool:
        # Cached across the WHOLE report, not just this alias. Remotely each
        # miss is a full ssh round trip, and ssh's seven default candidates
        # repeat for every alias — a 10-host registry would otherwise make
        # ~80 connections to answer ~8 distinct questions.
        if path not in cache:
            cache[path] = identity_exists(
                path,
                runner=runner,
                hop=hop,
                home=home,
                timeout=timeout,
                connect_timeout=connect_timeout,
            )
        return cache[path]

    missing = tuple(f for f in declared if not present(f))
    for path in missing:
        findings.append(
            Finding(
                record.name,
                alias,
                "missing-identity-file",
                "error",
                f"the stanza names {path}, which is not present. ssh will not "
                "offer it, and if no other key is offered the far end answers "
                "`Permission denied` even when the right key IS authorised "
                "there (the scitex-compute-01 fault, 2026-08-13).",
            )
        )

    usable = [f for f in identity_files if present(f)]
    if not usable:
        findings.append(
            Finding(
                record.name,
                alias,
                "no-key-offered",
                "error",
                "NONE of the identity files ssh would use exist here, so ssh "
                "offers no key at all.",
            )
        )

    declared_if = record.connectivity.identity_file
    if declared_if and declared_if not in identity_files:
        findings.append(
            Finding(
                record.name,
                alias,
                "identity-drift",
                "warning",
                f"the registry records `identity_file: {declared_if}` but ssh "
                f"resolves {list(identity_files)}.",
            )
        )

    return AliasCheck(
        record.name,
        alias,
        True,
        declared_hostname,
        effective_hostname,
        identity_files,
        declared,
        missing,
        identities_only,
        tuple(findings),
    )


def check_ssh_config(
    records,
    *,
    runner=run_command,
    config_file: str | Path | None = None,
    hop: str | None = None,
    home: Path | None = None,
    timeout: float = 15.0,
    connect_timeout: int = 5,
) -> SshConfigReport:
    """Compare the registry against what ssh actually resolves, here.

    Answers for the machine it RUNS ON (or, with ``hop``, for that peer) —
    an ssh config is per-machine, and the fault this catches lived in one
    host's own file. Sweeping the fleet means running it once per host.

    Never connects to the machine being described: ``ssh -G`` resolves and
    exits, so a switched-off host is still fully checkable.
    """
    records = list(records)
    home = home if home is not None else Path.home()
    builtin = builtin_identity_files(
        runner=runner, hop=hop, timeout=timeout, connect_timeout=connect_timeout
    )
    cache: dict[str, bool] = {}
    checks: list[AliasCheck] = []
    for record in records:
        conn = record.connectivity
        if conn.lan:
            checks.append(
                _check_alias(
                    record, record.name, conn.lan, runner=runner,
                    config_file=config_file, hop=hop, home=home,
                    builtin=builtin, cache=cache, timeout=timeout,
                    connect_timeout=connect_timeout,
                )
            )
        if conn.net:
            checks.append(
                _check_alias(
                    record, net_name(record.name), conn.net.hostname, runner=runner,
                    config_file=config_file, hop=hop, home=home,
                    builtin=builtin, cache=cache, timeout=timeout,
                    connect_timeout=connect_timeout,
                )
            )
    return SshConfigReport(
        on_host=hop or "localhost",
        checks=tuple(checks),
        baseline_available=bool(builtin),
    )


# EOF
