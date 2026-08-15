#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Is anything ONLINE that can actually run this job?

PS-224 already asks whether a ``runs-on`` destination is REGISTERED — whether
the machine registry knows a machine carrying those labels. That question is
static, offline, and correct, and it is NOT this one.

REGISTRY MEMBERSHIP IS NOT LIVENESS, and the gap between them is what an outage
lives in. Measured 2026-08-15:

    49 repositories pinned CI_RUNS_ON to `spartan-cpu`
    80 workflow references fell back to `scitex-ci` across 14 repositories
    every ORG runner carrying either label was OFFLINE
    PS-224 reported nothing, correctly — both labels ARE in the registry

So the auditor was satisfied while no job could start. GitHub does not reject a
job whose labels nothing serves; it QUEUES IT FOREVER, which is indistinguishable
from waiting behind a busy runner. Neither state reports.

WHY THIS IS NOT AN AUDIT RULE
------------------------------
An audit rule runs offline, in CI, against a checkout. Putting a live API query
inside one makes the gate network-dependent: it goes red when the API
rate-limits, and that failure reads as a code problem to whoever is looking. That
trades a silent hole for a noisy one, and noisy gates get ignored.

The separation kept here: **the auditor validates the repository, this probe
validates the machines.** It is meant to run on a schedule and report, not to
block a pull request.

THE THIRD VALUE IS THE POINT
-----------------------------
A probe that cannot reach the API must say UNKNOWN. Reporting "unserved" would
raise a false outage every time GitHub hiccups; reporting "served" would restore
the exact silence this exists to break. Both poles are wrong, so
:func:`classify_label` has three outcomes and the caller is handed the
distinction rather than a boolean.
"""

from __future__ import annotations

from enum import Enum
from typing import Final, Iterable, NamedTuple, Sequence

#: A runner is only useful if it is ONLINE. `busy` is fine — a busy runner
#: drains its queue — so busyness is deliberately NOT part of the predicate.
#: Conflating them would report a healthy, saturated pool as an outage, which is
#: what figrecipe correctly distinguished when they separated QUEUE time from
#: EXECUTION time on 2026-08-15.
ONLINE: Final[str] = "online"


class Liveness(Enum):
    """Whether a destination can be executed, and why we say so."""

    SERVED = "served-by-an-online-runner"
    UNSERVED = "no-online-runner-carries-these-labels"
    UNKNOWN = "runner-inventory-unavailable"


class Runner(NamedTuple):
    """One registered runner, as the Actions API reports it."""

    name: str
    status: str
    labels: frozenset[str]

    @property
    def is_online(self) -> bool:
        return self.status == ONLINE


class LabelVerdict(NamedTuple):
    """The answer for ONE destination, with the evidence attached."""

    labels: frozenset[str]
    liveness: Liveness
    carriers: tuple[str, ...] = ()

    @property
    def blocks(self) -> bool:
        """True only for a destination we PROVED nothing can run.

        UNKNOWN deliberately does not block: an unreachable API is a broken
        instrument, not an outage, and reporting it as one trains the reader to
        ignore the alarm that matters.
        """
        return self.liveness is Liveness.UNSERVED


def parse_runners(payload: object) -> tuple[Runner, ...] | None:
    """Parse ``gh api /orgs/<org>/actions/runners`` into runners.

    Returns ``None`` — never ``()`` — for anything that is not a recognisable
    runner list. An empty tuple means "the API answered and the org has no
    runners", which is a real and different fact; conflating the two is how a
    failed lookup becomes a clean bill of health.

    That distinction is not hypothetical. Measured 2026-08-15: ``gh api``
    printed a 404 BODY to stdout, an emptiness test never fired, and 76
    repositories were recorded as having a variable when 8 had none.
    """
    if not isinstance(payload, dict):
        return None
    rows = payload.get("runners")
    if not isinstance(rows, list):
        return None
    out: list[Runner] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        name, status = row.get("name"), row.get("status")
        labels = row.get("labels")
        if not isinstance(name, str) or not isinstance(status, str):
            return None
        if not isinstance(labels, list):
            return None
        names = {lb.get("name") for lb in labels if isinstance(lb, dict)}
        if any(n is None for n in names):
            return None
        out.append(Runner(name=name, status=status, labels=frozenset(names)))
    return tuple(out)


def classify_label(
    labels: Iterable[str], runners: Sequence[Runner] | None
) -> LabelVerdict:
    """Decide whether any ONLINE runner can serve ``labels``.

    A runner serves a destination when its label set is a SUPERSET of the
    required labels — that is how GitHub matches, and it is why
    ``[self-hosted, Linux, X64, scitex-ci]`` is not served by a machine
    carrying only ``scitex-ci``.
    """
    required = frozenset(labels)
    if runners is None:
        return LabelVerdict(required, Liveness.UNKNOWN)
    carriers = tuple(
        r.name for r in runners if r.is_online and required <= r.labels
    )
    if carriers:
        return LabelVerdict(required, Liveness.SERVED, carriers)
    return LabelVerdict(required, Liveness.UNSERVED)


class ProbeReport(NamedTuple):
    """Every destination's verdict, in a fixed shape (§2)."""

    verdicts: tuple[LabelVerdict, ...] = ()

    @property
    def unserved(self) -> tuple[LabelVerdict, ...]:
        return tuple(v for v in self.verdicts if v.blocks)

    @property
    def unknown(self) -> tuple[LabelVerdict, ...]:
        return tuple(v for v in self.verdicts if v.liveness is Liveness.UNKNOWN)


def probe(
    destinations: Iterable[Iterable[str]], runners: Sequence[Runner] | None
) -> ProbeReport:
    """Classify every destination, deduped and in a stable order."""
    seen: dict[frozenset[str], None] = {}
    for d in destinations:
        seen.setdefault(frozenset(d), None)
    ordered = sorted(seen, key=lambda s: sorted(s))
    return ProbeReport(tuple(classify_label(d, runners) for d in ordered))


def render(report: ProbeReport) -> str:
    """Render for a human, saying plainly when nothing could be judged."""
    if not report.verdicts:
        return "no runner destinations found to check"
    lines = [
        f"{'/'.join(sorted(v.labels))}: {v.liveness.value}"
        + (f" ({', '.join(v.carriers)})" if v.carriers else "")
        for v in report.verdicts
    ]
    if report.unknown:
        lines.append(
            f"WARNING: {len(report.unknown)} destination(s) COULD NOT BE JUDGED "
            "— the runner inventory was unavailable. This is not a clean "
            "result; re-run when the API is reachable."
        )
    lines.append(
        f"{len(report.verdicts)} destination(s), {len(report.unserved)} with no "
        "online carrier"
    )
    return "\n".join(lines)


# EOF
