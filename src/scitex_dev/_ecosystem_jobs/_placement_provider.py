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
    ]


__all__ = ["provide_placement"]

# EOF
