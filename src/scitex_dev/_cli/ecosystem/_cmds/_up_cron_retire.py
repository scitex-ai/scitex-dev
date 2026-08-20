#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Retire the managed crontab block. Cron is no longer a deploy target.

CRON IS RETIRED FOR SciTeX PERIODIC JOBS. Every periodic job — timer-kind
AND cron-kind — runs in-process in the supervisor's
:class:`scitex_dev._supervisor._periodic.PeriodicRunner`, which
``SupervisorRuntime.reconcile()`` ticks on the same clock as the service
children.

Operator ruling, 2026-08-20:

    「サイテクス系の定期ジョブは全てスーパーバイザー経由でサイテクスデブ
      で一本化」

— every SciTeX periodic job goes through the supervisor, via scitex-dev,
and nowhere else. Recorded as ADR-0012.

WHY THIS MODULE REPLACES AN INSTALLER
-------------------------------------
``ecosystem up`` used to INSTALL this block, and that is precisely what
made a second scheduler possible. Measured 2026-08-19: a peer ran
``ecosystem up --yes`` across four hosts, installing 29-35 crontab
entries per host — every one of those jobs was already running in-process
under the supervisor, with 32,000-40,000 execution records to prove it.
The operator stopped it: 「クロンは使わないと言う話でしたよね」.

The peer's action was reasonable and their reading of the command was
correct. This code path is what made a correct action wrong.

So ``up`` now CONVERGES the host to the declaration rather than away
from it. The managed block's correct content is EMPTY, and a reconcile
that left a stale block in place would preserve exactly the double
management it exists to prevent — the failure state is a host that has
both, not a host that has neither.

BLAST RADIUS
------------
Only the ``BEGIN``/``END`` managed block is touched. scitex-dev owns that
region; everything else in the user's crontab is somebody else's and is
passed through untouched by ``strip_block``.
"""

from __future__ import annotations

from typing import Callable


def retire_cron_block(
    *,
    yes: bool,
    echo: Callable[[str], None],
) -> int:
    """Remove the managed crontab block. Returns the number of lines removed.

    Reports and returns 0 without ``yes``, matching what installing did:
    a reconcile that mutates the crontab without ``--yes`` would be a
    surprise, and this one is destructive.
    """
    from ....jobs import _cron_block as cb
    from ...cron import _crontab

    try:
        current = _crontab.read_crontab()
    except RuntimeError as exc:
        # Never wedge the reconcile: the supervisor half is what keeps
        # the host working, and it does not depend on the crontab.
        echo(f"cron: ERROR reading crontab: {exc}")
        return 0

    # Ask whether a block is PRESENT, not whether stripping changed the
    # text. `strip_block` also normalises the trailing newline, so
    # `stripped != current` is true on a host that never had a block —
    # and using that as the predicate rewrote an innocent crontab. The
    # marker is the thing; text inequality was a proxy for it.
    if cb.BLOCK_BEGIN not in current:
        # Said explicitly rather than silently: on a host that never had
        # one this is the correct state, and a silent pass would be
        # indistinguishable from a failed read, which also writes nothing.
        echo("cron: no managed block present (correct — cron is retired)")
        return 0

    stripped = cb.strip_block(current)

    removed = len(current.splitlines()) - len(stripped.splitlines())
    if not yes:
        echo(
            f"cron: {removed} managed line(s) are RETIRED and would be "
            f"removed; --yes required to remove them"
        )
        return 0

    # `crontab -` REFUSES input without a trailing newline:
    #   "new crontab file is missing newline before EOF, can't install."
    # `strip_block` ends with `.rstrip("\n")`, so its output never has one.
    #
    # MEASURED on ywata-note-win 2026-08-20: the retirement failed on the
    # ONLY host that had a managed block, leaving all 37 lines in place
    # while every other host reported success — because those hosts had
    # nothing to write and returned before reaching this call. The bug was
    # therefore invisible on 4 of 5 hosts, and the one host it broke is the
    # one the feature exists for.
    #
    # Not fixed in `strip_block`: that helper is also used where a trailing
    # newline would be wrong, and this is the crontab writer's requirement,
    # so it belongs at the boundary that talks to `crontab`.
    if not stripped.endswith("\n"):
        stripped += "\n"

    try:
        _crontab.write_crontab(stripped)
    except RuntimeError as exc:
        echo(f"cron: ERROR writing crontab: {exc}")
        return 0

    echo(
        f"cron: removed {removed} managed line(s) — periodic jobs run in "
        f"the supervisor, not cron (ADR-0012)"
    )
    return removed


__all__ = ["retire_cron_block"]

# EOF
