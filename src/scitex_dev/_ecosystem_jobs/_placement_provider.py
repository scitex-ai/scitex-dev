#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex-dev's own host-placement declaration.

The mechanism ships WITH a non-empty declaration from its owner, on
purpose. Two federation surfaces already exist and are effectively
unadopted — ``scitex_dev.system_deps`` has 2 providers across ~64
packages, and sac's host-side job selection was UNSTATED on 4 of 4
hosts. A third declaration surface that nobody is required to fill in
helps nobody, so this one is exercised by its author on day one rather
than shipped empty and hoped for.

WHAT IS DECLARED HERE, AND WHAT DELIBERATELY IS NOT
---------------------------------------------------
Only jobs whose placement is a genuine FACT about the fleet. A job that
should run everywhere is left UNDECLARED rather than written as
``hosts="*"``: undeclared already arms everywhere, so declaring it would
add a line that changes nothing while implying somebody made a decision.
The declaration is for jobs that must run on ONE host — where running
them on several is duplicated work, or worse.

``scitex-dev-deploy-freshness`` is the case in point. It reconciles what
is deployed against what is released, fleet-wide. Run on four hosts it
does the same reconciliation four times and can report four times, which
is how a useful signal becomes noise the operator learns to ignore.
"""

from __future__ import annotations

from ..jobs._placement import PlacementRecord

#: The host that carries scitex-dev's singleton control-plane jobs.
#:
#: Named explicitly rather than by group because host groups are not yet
#: declared anywhere machine-readable (sac measured their peer table as
#: carrying only ``ssh`` / ``env_preamble`` / ``via``). When ``groups:``
#: lands on the peer entries this can become ``groups=("infra",)``, and
#: the resolver already supports it.
_CONTROL_PLANE_HOST = "scitex-compute-04"


def provide_placement() -> list[PlacementRecord]:
    """Return scitex-dev's placement records for the federation.

    Loaded by ``scitex_dev.jobs._placement.discover_placement()`` through
    the ``scitex_dev.host_placement`` entry-point group — scitex-dev's
    own pyproject.toml declares this provider like any other leaf.
    """
    return [
        # Fleet-wide reconciliation: one host, or the same answer is
        # computed and reported N times.
        PlacementRecord(
            job="scitex-dev-deploy-freshness",
            hosts=(_CONTROL_PLANE_HOST,),
        ),
        # ci-watch polls a FIXED map of repos over the GitHub API. Every
        # host it runs on asks the same question about the same five
        # repositories and gets the same answer, so the duplication buys
        # nothing and is spent from a budget shared with every other
        # agent in the fleet.
        #
        # MEASURED 2026-08-20, during a live exhaustion of that shared
        # account:
        #     AGENTS_TO_REPOS         5 repos
        #     1 gh call per repo      ("last 12 develop-branch runs")
        #     */10 -> 6 runs/hour
        #     running on 4 hosts      (226 / 500 / 836 / 1114 executions)
        #     = 120 calls/hour ~ 2.0/min, against ~72/min unaccounted for
        # One host cuts that to 30/hour with IDENTICAL coverage: the four
        # copies are not redundancy, nobody designed them as failover, and
        # no single host's view reveals that the other three exist.
        #
        # Why this is not "stop the job": scitex-agent-container had
        # already turned their CI verdict ring off fleet-wide, so stopping
        # this one too would have made CI feedback completely dark — and
        # ci-result-notify-agents-via-channel records an hour of merging
        # onto red because nothing said so. Removing duplication keeps the
        # signal; removing the job trades one outage for another.
        PlacementRecord(
            job="ci-watch",
            hosts=(_CONTROL_PLANE_HOST,),
        ),
        # A REMOTE ref is shared. Seven hosts sweeping origin is seven
        # times the API calls for one effect, and the six that lose the
        # race each report a failure for a branch the winner already
        # deleted — noise that is indistinguishable from the sweep being
        # broken. Its sibling `scitex-dev-branch-hygiene` (the LOCAL leg)
        # is deliberately NOT placed: every host has its own checkouts,
        # so undeclared-arms-everywhere is exactly right there.
        PlacementRecord(
            job="scitex-dev-branch-hygiene-remote",
            hosts=(_CONTROL_PLANE_HOST,),
        ),
    ]


__all__ = ["provide_placement"]

# EOF
