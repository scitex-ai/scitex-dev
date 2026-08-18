#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure JobSpec helpers: ``kind="timer"`` → ``kind="cron"`` translation.

Extracted from ``_up.py`` to keep the orchestrator under the line-cap
and to let the (pure) translation logic be unit-tested without booting
the rest of the up flow.

The federated ``_cron_block.upsert_block`` helper only understands
``kind="cron"`` JobSpecs (5-field cron expressions). Per the supervisor
redesign (operator policy 2026-06-14), ``kind="timer"`` jobs no longer
lower to systemd timer units — they lower to cron lines instead. This
module is the translator. Each timer JobSpec becomes a synthetic
``kind="cron"`` JobSpec whose ``schedule`` is the best-effort cron
expression derived from the timer's ``on_unit_active_sec`` / ``schedule``.

WHICH properties a lowering drops, and how badly, now lives in the
sibling :mod:`._up_timer_losses` — re-exported below so this module
remains the single import site for the whole lowering surface.

This module deliberately does NOT decide whether timer-kind *should*
lower to cron at all (open question with the operator), and it does NOT
wrap the command — a ``flock``-style prefix would strand the inner
console script on systemd's minimal PATH, because
``resolve_execstart`` absolutises only the first token. Enforcement by
wrapper is a separate design.
"""

from __future__ import annotations

from typing import Callable

from ....jobs import JobSpec
from ._up_timer_losses import (
    TARGET_SURFACE,
    DroppedProperty,
    TimerLoweringError,
    accounted_fields,
    advisory_losses,
    blocking_losses,
    command_is_wrappable,
    cron_command_for,
    format_degraded_report,
    format_loss_report,
    jobspec_field_names,
    lowering_losses,
)


def timer_to_cron_jobspec(
    job: JobSpec, *, allow_lossy: bool = False
) -> JobSpec:
    """Lower a ``kind="timer"`` JobSpec to a synthetic ``kind="cron"`` one.

    Translation rules (first match wins):

    * ``job.schedule`` already a 5-field cron expression → preserved.
    * ``on_unit_active_sec`` ``"<N>min"`` → ``"*/N * * * *"`` (1≤N≤59).
    * ``on_unit_active_sec`` ``"<N>h"``   → ``"0 */N * * *"`` (1≤N≤23).
    * ``on_unit_active_sec`` ``"<N>d"``   → ``"0 0 */N * *"`` (1≤N≤30).
    * Anything else → ``"0 * * * *"`` (hourly fallback).

    The returned JobSpec carries ``kind="cron"`` so it lands cleanly
    in :func:`scitex_dev.jobs._cron_block.upsert_block`. ``description``
    is preserved so ``crontab -l`` stays legible.

    Raises :class:`TimerLoweringError` when ``job`` declares a property
    cron cannot carry (see :func:`lowering_losses`) — a declared
    guarantee is never dropped silently. ``allow_lossy=True`` is the
    explicit, caller-side opt-in to the degraded lowering; callers that
    set it are expected to REPORT the losses (``ecosystem up`` does).
    """
    if not allow_lossy:
        losses = blocking_losses(job)
        if losses:
            raise TimerLoweringError(job.name, losses)

    return JobSpec(
        name=job.name,
        kind="cron",
        schedule=derive_cron_expr(job),
        command=cron_command_for(job),
        description=job.description,
    )


def derive_cron_expr(job: JobSpec) -> str:
    """Inner cron-expression derivation. Pure — no I/O."""
    fields_ = job.schedule.split()
    if len(fields_) == 5:
        return job.schedule

    cad = (job.on_unit_active_sec or "").strip().lower()
    if cad.endswith("min"):
        n = _safe_int(cad[:-3])
        if n and 1 <= n <= 59:
            return f"*/{n} * * * *"
    if cad.endswith("h"):
        n = _safe_int(cad[:-1])
        if n and 1 <= n <= 23:
            return f"0 */{n} * * *"
    if cad.endswith("d"):
        n = _safe_int(cad[:-1])
        if n and 1 <= n <= 30:
            return f"0 0 */{n} * *"
    # Hourly fallback catches "the leaf forgot to set a cadence" without
    # busy-spinning. Operators prefer a noisy-but-bounded job over a
    # silently-dropped one.
    return "0 * * * *"


def _safe_int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None


def collect_cron_jobs(
    jobs: list[JobSpec],
    *,
    allow_lossy: bool = False,
    on_degrade: Callable[[str], None] | None = None,
    on_refuse: Callable[[TimerLoweringError], None] | None = None,
) -> tuple[list[JobSpec], int, int]:
    """Return ``(merged, cron_native_count, timer_lowered_count)``.

    The merged list is what gets handed to
    :func:`scitex_dev.jobs._cron_block.upsert_block` — one block,
    mixed cron-native + lowered-timer entries. The counts come back
    so the orchestrator's summary line is honest about WHERE each
    cron entry came from.

    Raises :class:`TimerLoweringError` on the FIRST timer whose declared
    properties cron cannot honour. ``allow_lossy=True`` proceeds
    instead, calling ``on_degrade`` once per degraded job with the full
    loss report — the degraded path is explicit and noisy, never
    silent.

    ``on_refuse`` makes the refusal PER-JOB instead of per-run: the
    unlowerable timer is left out of the merged block and handed to the
    callback, and every other job still installs. Without it the first
    bad JobSpec aborts the whole reconcile.

    That default is a blast radius, not a guarantee. Measured fleet-wide
    2026-08-19 on scitex-dev 0.55.0: ONE JobSpec declaring
    ``timeout_sec=120`` (which cron cannot carry) meant THREE hosts got
    zero cron entries and the fourth kept nine STALE lines written by an
    older release — because every subsequent run aborted before
    rewriting the block, freezing the drift it was supposed to correct.
    Thirty-three well-formed jobs were undeployed to punish one
    malformed one.

    Refusing to install a WEAKER artifact under a job's own name is
    right, and ``on_refuse`` keeps that intact — the refused job is
    still not installed, still reported, and the caller is expected to
    exit non-zero. What it drops is the claim that one leaf's bad
    declaration should decide whether every OTHER leaf gets deployed.
    Same correction as the supervisor decoupling one layer up: keep the
    refusal, shrink what it takes hostage.
    """
    cron_native = [j for j in jobs if j.kind == "cron"]
    timer_jobs = [j for j in jobs if j.kind == "timer"]

    lowered: list[JobSpec] = []
    for timer in timer_jobs:
        if on_degrade is not None:
            _report(timer, allow_lossy=allow_lossy, on_degrade=on_degrade)
        try:
            lowered.append(
                timer_to_cron_jobspec(timer, allow_lossy=allow_lossy)
            )
        except TimerLoweringError as exc:
            if on_refuse is None:
                raise
            on_refuse(exc)

    return cron_native + lowered, len(cron_native), len(lowered)


def _report(
    timer: JobSpec,
    *,
    allow_lossy: bool,
    on_degrade: Callable[[str], None],
) -> None:
    """Echo advisory notices, plus degradation reports when opted in.

    Advisory losses are reported ALWAYS — they never block, but they
    are never silent either, which is the whole point of this module.
    """
    for loss in advisory_losses(timer):
        on_degrade(
            f"cron: NOTICE lowering timer {timer.name!r} onto "
            f"{TARGET_SURFACE} drops {loss.field}={loss.declared!r}: "
            f"{loss.consequence}"
        )
    if allow_lossy:
        blocking = blocking_losses(timer)
        if blocking:
            on_degrade(
                "cron: DEGRADED (--allow-lossy-timer-lowering): "
                + format_degraded_report(timer.name, blocking)
            )


def degraded_job_names(jobs: list[JobSpec]) -> list[str]:
    """Names of timer jobs that would lose a GUARANTEE on lowering. Pure."""
    return [j.name for j in jobs if blocking_losses(j)]


__all__ = [
    "TARGET_SURFACE",
    "DroppedProperty",
    "TimerLoweringError",
    "accounted_fields",
    "advisory_losses",
    "blocking_losses",
    "collect_cron_jobs",
    "command_is_wrappable",
    "cron_command_for",
    "degraded_job_names",
    "derive_cron_expr",
    "format_degraded_report",
    "format_loss_report",
    "jobspec_field_names",
    "lowering_losses",
    "timer_to_cron_jobspec",
]


# EOF
