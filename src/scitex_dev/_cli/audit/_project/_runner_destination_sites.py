# -*- coding: utf-8 -*-
"""PS-224 site keys, exemption recipes, and destination union.

Extracted from ``_check_runner_destinations`` (512-line budget). These three
concern how a finding is ADDRESSED — where it points, how a user silences it,
and which destinations count as registered — as distinct from the check that
decides whether to emit one. The checker imports them back, so the public
surface of ``_check_runner_destinations`` is unchanged.
"""

from __future__ import annotations

#: Separator between a workflow path and a job id in a site key.
_SITE_SEP = "::"

#: PS-224 findings are per-JOB, not per-line, so both the emitted site and
#: any `audit.exemptions` entry pin line 0 (same contract as PS-222).
_NO_LINE = 0


def _site(rel: str, job_id: str | None = None) -> str:
    """Site key for a finding: ``path`` or ``path::job-id``.

    This exact string is BOTH the finding's reported location AND what an
    ``audit.exemptions`` entry's ``path`` must spell, so the instruction a
    user reads is the instruction that works.
    """
    return rel if job_id is None else f"{rel}{_SITE_SEP}{job_id}"


def _exempt_hint(site: str) -> str:
    """The copy-pasteable exemption recipe for one site (reason MANDATORY)."""
    return (
        " If this job genuinely cannot run on any registered machine, exempt "
        "THIS JOB (never the whole file) in `.scitex/dev/config.yaml` under "
        f"`audit: exemptions: PS-224:` with `path: {site}`, `line: 0` and a "
        "`reason:` saying why — the reason is mandatory (constitution §2), "
        "and a blank one exempts nothing."
    )


def _union_destinations(
    floor: list[tuple[str, frozenset[str]]],
    user_state: list[tuple[str, frozenset[str]]],
) -> list[tuple[str, frozenset[str]]]:
    """FLOOR ∪ user-state, order-stable and de-duplicated.

    The shipped seed comes FIRST (it is the floor), then any user-state
    destination the floor does not already carry. A destination present in
    both — the common case, since the user file is usually a copy of the
    seed — appears exactly ONCE, so the "Registered destinations:" line the
    error prints does not list it twice.
    """
    out: list[tuple[str, frozenset[str]]] = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for host, labels in (*floor, *user_state):
        key = (host, labels)
        if key in seen:
            continue
        seen.add(key)
        out.append((host, labels))
    return out


__all__ = ["_SITE_SEP", "_NO_LINE", "_site", "_exempt_hint", "_union_destinations"]

# EOF
