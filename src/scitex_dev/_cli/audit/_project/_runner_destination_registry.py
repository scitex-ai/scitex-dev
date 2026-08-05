# -*- coding: utf-8 -*-
"""Resolve the set of REGISTERED runner destinations PS-224 validates against.

The registry is the shipped seed (``scitex_dev.hosts._seed``) UNIONed with the
host's user-state ``~/.scitex/dev/hosts.yaml`` — the seed is an unconditional
FLOOR that per-host state may only EXTEND, never subtract from.

Why a union and not a fallback
-------------------------------
The first implementation read the seed only WHEN the user registry was empty.
That let per-host mutable state SUBTRACT from the gate's ground truth: a host
that registered even ONE unrelated machine REPLACED the shipped seed entirely,
hiding registered destinations and turning correctly-targeted jobs red. Because
the file is edited live, the gate's verdict then moved under repos that changed
nothing — measured 2026-07-29 in scitex-agent-container, where the same tree
passed at 14:56 and failed after a 15:07 edit to ``hosts.yaml``, with no code
change in the audited area.

A central gate must validate against SSOT data shipped IN the package as a
floor. This is not a softening: both sides supply real, measured destinations,
and a job whose labels NEITHER side serves still errors.
"""

from __future__ import annotations


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


__all__ = ["_union_destinations"]

# EOF
