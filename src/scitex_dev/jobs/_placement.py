#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Which host ARMS which job — the repo-side placement declaration.

A ``JobSpec`` is a fleet-wide declaration with no host axis. Every
discovered job is therefore a candidate on every host, and "which of
these should run HERE" has been answered only by the host's systemd
enablement: invisible state, on nine hosts, with no declaration to
compare it against.

Measured consequence, 2026-08-19: scitex-compute-02 and -03 had no
supervisor at all. Not a failure — nothing anywhere said they should
have one, so nobody was wrong. It was closed by hand over ssh, which is
the opposite of "the repo is the source and the machine is reproduced
from it".

This module is the missing axis. Placement is declared in the REPO, via
the ``scitex_dev.host_placement`` entry-point group, mirroring the
``scitex_dev.jobs`` federation exactly.

Design agreed with scitex-agent-container (sac), 2026-08-19, who own the
host topology and the agent specs. Two of their requirements are load
bearing and are pinned by tests:

THREE STATES, NEVER TWO
-----------------------
``PLACED`` / ``EXCLUDED`` / ``UNSTATED``, and **UNSTATED arms
everything**. In sac's words, from the host-side selection module this
replaces:

    "A host that has never been configured must not have its timers
    silently disarmed by the arrival of this feature; a host that
    deliberately selected nothing must not have them armed. Collapsing
    those two into an empty set is how a safety feature becomes an
    outage."

Collapse the third state and the ROLLOUT of this feature is itself the
outage: every host that has not yet declared placement gets disarmed the
moment the code ships. The distinction is per-JOB, not per-fleet — a job
nobody has placed is UNSTATED even while its neighbours are placed.

GATE ARMING, NOT INSTALLING
---------------------------
An unplaced job is still INSTALLED, just not armed. The unit stays
inspectable with ``systemctl cat``, and ``ecosystem up`` keeps answering
"what could this host run?" honestly. Refusing to install would hide the
job from the very command an operator uses to ask.

THE GROUPS BRANCH REFUSES RATHER THAN NO-OPS
--------------------------------------------
Placement may name ``groups`` instead of explicit hosts. sac measured
that their peer table (``~/.scitex/agent-container/config.yaml``) has no
group field at all — ``ssh``, ``env_preamble``, ``via`` is the whole
vocabulary — so a group branch shipped today would never match, fall
through to UNSTATED, arm everything, and *look* like it worked. A
decorative branch in a placement resolver is worse than no branch.

So: naming a group while the host declares NO groups whatsoever is a
:class:`PlacementUnresolvable`, not a silent fall-through. sac is adding
``groups:`` to the peer entries; until that lands, a group-placed job
fails loudly instead of quietly arming everywhere.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

#: Entry-point group. Mirrors ``scitex_dev.jobs``:
#:
#:     [project.entry-points."scitex_dev.host_placement"]
#:     mypkg = "mypkg._jobs:get_placement"
#:
#: The callable takes no arguments and returns a list of
#: :class:`PlacementRecord`.
ENTRY_POINT_GROUP = "scitex_dev.host_placement"

#: ``hosts="*"`` — this job belongs on every host.
PLACE_EVERYWHERE = "*"

# --------------------------------------------------------------------------- #
# The three states                                                             #
# --------------------------------------------------------------------------- #

#: Declared for this host: ARM it.
PLACED = "placed"

#: Declared, and this host is not among the targets: do NOT arm it.
EXCLUDED = "excluded"

#: Nobody declared anything about this job: ARM it.
#:
#: NOT the same as EXCLUDED, and the whole point of the module. An empty
#: declaration means "no opinion yet", never "run nothing here".
UNSTATED = "unstated"


class PlacementUnresolvable(RuntimeError):
    """A placement names a group, and no host group is declared anywhere.

    Raised instead of falling through to UNSTATED. Falling through would
    arm the job everywhere while appearing to honour a group
    restriction — the failure would be invisible precisely because the
    safe default is also the permissive one.
    """

    def __init__(self, job_name: str, groups: Sequence[str], host: str):
        self.job_name = job_name
        self.groups = tuple(groups)
        self.host = host
        super().__init__(
            f"placement for job {job_name!r} names group(s) "
            f"{', '.join(groups)}, but host {host!r} declares no groups at "
            f"all, so the restriction cannot be evaluated.\n"
            f"This is refused rather than ignored: ignoring it would ARM "
            f"the job here while looking like it had been restricted.\n"
            f"Fix: declare this host's groups (sac owns the peer table — "
            f"`groups:` on the host's entry, surfaced through "
            f"`sac host list --json`), or place the job by explicit "
            f"`hosts=[...]` instead of by group."
        )


@dataclass(frozen=True)
class PlacementRecord:
    """One declaration of where a job belongs. Pure data.

    ``hosts`` wins over ``groups`` when both are given — an explicit
    host list is the more specific statement, and a reader should not
    have to work out which of two overlapping rules applied.
    """

    job: str
    hosts: tuple[str, ...] | str | None = None
    groups: tuple[str, ...] | None = None

    def targets_everywhere(self) -> bool:
        """True when this record places the job on every host. Pure."""
        return self.hosts == PLACE_EVERYWHERE


@dataclass(frozen=True)
class PlacementDecision:
    """Why a job is or is not armed here. Pure data.

    Carries the REASON, not just the verdict: an operator asking why a
    job did not start on a host needs to tell "excluded by declaration"
    from "nobody said anything", and those two produce opposite fixes.
    """

    job: str
    state: str
    reason: str
    armed: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "armed", self.state != EXCLUDED)


def _as_tuple(value: Iterable[str] | str | None) -> tuple[str, ...]:
    """Normalise a hosts/groups field to a tuple. Pure."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def decide(
    job_name: str,
    records: Sequence[PlacementRecord],
    *,
    host: str,
    host_groups: Sequence[str] = (),
) -> PlacementDecision:
    """Decide whether ``job_name`` is armed on ``host``. Pure.

    ``records`` is every placement record discovered fleet-wide, not
    only this job's — the function selects. ``host_groups`` is what
    THIS host declares about itself; empty means "declares nothing",
    which is what makes a group-named placement unresolvable rather
    than merely unmatched.
    """
    mine = [r for r in records if r.job == job_name]
    if not mine:
        return PlacementDecision(
            job=job_name,
            state=UNSTATED,
            reason=(
                "no placement declared for this job anywhere; arming it, "
                "because an absent declaration is 'no opinion yet', not "
                "'run nothing here'"
            ),
        )

    for record in mine:
        if record.targets_everywhere():
            return PlacementDecision(
                job=job_name,
                state=PLACED,
                reason=f"placed on every host (hosts={PLACE_EVERYWHERE!r})",
            )

        hosts = _as_tuple(record.hosts)
        if hosts and host in hosts:
            return PlacementDecision(
                job=job_name,
                state=PLACED,
                reason=f"{host} is named explicitly in hosts",
            )

        groups = _as_tuple(record.groups)
        if groups:
            if not host_groups:
                raise PlacementUnresolvable(job_name, groups, host)
            overlap = sorted(set(groups) & set(host_groups))
            if overlap:
                return PlacementDecision(
                    job=job_name,
                    state=PLACED,
                    reason=f"{host} is in group(s) {', '.join(overlap)}",
                )

    return PlacementDecision(
        job=job_name,
        state=EXCLUDED,
        reason=(
            f"placement is declared for this job, and {host} is not among "
            f"its targets"
        ),
    )


def _iter_entry_points(group: str):
    """Yield entry points for ``group``, compatible with Python 3.9+."""
    from importlib.metadata import entry_points

    if sys.version_info >= (3, 10):
        return entry_points(group=group)
    eps = entry_points()
    return eps.get(group, [])


def discover_placement(
    *,
    extra_providers: list[Callable[[], list[PlacementRecord]]] | None = None,
) -> list[PlacementRecord]:
    """Aggregate every :class:`PlacementRecord` across the ecosystem.

    Mirrors :func:`scitex_dev.jobs.discover_jobs` deliberately — same
    entry-point federation, same "a broken provider is skipped with a
    warning rather than wedging the aggregation" contract, same
    ``extra_providers`` test seam.

    One deliberate DIFFERENCE from ``discover_jobs``: placement records
    are NOT de-duplicated by job name. Two packages may each place the
    same job, and first-wins would silently drop the second — here the
    records accumulate and :func:`decide` reads them all, so a job
    placed on 02 by one provider and on 03 by another runs on both.
    """
    import logging

    logger = logging.getLogger(__name__)
    providers: list[Callable[[], list[PlacementRecord]]] = []

    for ep in _iter_entry_points(ENTRY_POINT_GROUP):
        providers.append(_make_ep_provider(ep))

    if extra_providers:
        providers.extend(extra_providers)

    records: list[PlacementRecord] = []
    for provider in providers:
        try:
            produced = provider()
        except Exception:
            logger.warning(
                "Failed to load placement from provider %r",
                provider,
                exc_info=True,
            )
            continue
        for record in produced:
            if not isinstance(record, PlacementRecord):
                logger.warning(
                    "Provider %r yielded a non-PlacementRecord %r; skipping",
                    provider,
                    record,
                )
                continue
            records.append(record)

    return records


def _make_ep_provider(ep) -> Callable[[], list[PlacementRecord]]:
    """Wrap an entry point into a provider callable. Pure factory."""

    def _provider() -> list[PlacementRecord]:
        get_placement = ep.load()
        return list(get_placement())

    _provider.__name__ = f"entry_point:{getattr(ep, 'name', '?')}"
    return _provider


__all__ = [
    "ENTRY_POINT_GROUP",
    "EXCLUDED",
    "PLACED",
    "PLACE_EVERYWHERE",
    "UNSTATED",
    "PlacementDecision",
    "PlacementRecord",
    "PlacementUnresolvable",
    "decide",
    "discover_placement",
]

# EOF
