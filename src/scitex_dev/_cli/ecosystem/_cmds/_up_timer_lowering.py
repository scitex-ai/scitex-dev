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

Lossy lowering must be LOUD
---------------------------
A cron line is ``<schedule> <command> # marker`` and nothing else — see
:func:`scitex_dev.jobs._cron_block.build_cron_line`, which reads only
``schedule`` / ``command`` / ``name``. Every other systemd-flavoured
field a timer JobSpec may declare is therefore **unrepresentable** on
the crontab surface.

Historically the lowering just dropped them. A JobSpec declaring
``timeout_sec=300`` deployed as an *unbounded* cron line under the SAME
name, with nothing reported — the registry kept a promise the
deployment could not honour. Measured consequence (2026-07-18):
``sac.fleet-reconcile`` accumulated fourteen concurrent instances, the
oldest 45 minutes old, because nothing bounded a run.

So the lowering now REFUSES by default when a declared GUARANTEE cannot
survive the trip (:class:`TimerLoweringError`), and the degraded path is
an explicit, per-job-reported opt-in (``allow_lossy=True``). The
"which properties are lost" computation is the pure, side-effect-free
:func:`lowering_losses`.

Two tiers, both reported, only one blocking:

* **blocking** (``timeout_sec``, ``venv``) — a dropped guarantee. The
  deployed artifact is genuinely weaker than the registry claims, so
  the reconcile refuses.
* **advisory** (``on_boot_sec``) — a dropped preference. Echoed on
  every run, never blocking. Measured on the live fleet 2026-07-19,
  ALL 10 timer JobSpecs drop something but only 7 drop a guarantee;
  refusing on all 10 would make the opt-in flag permanent, which is
  how a loud check decays back into a silent one.

This module deliberately does NOT decide whether timer-kind *should*
lower to cron at all (open question with the operator), and it does NOT
wrap the command — a ``flock``-style prefix would strand the inner
console script on systemd's minimal PATH, because
``resolve_execstart`` absolutises only the first token. Enforcement by
wrapper is a separate design.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Callable

from ....jobs import JobSpec

#: Human name of the surface a lowered timer lands on. Used in error
#: text so the operator knows WHERE the guarantee is being dropped.
TARGET_SURFACE = "the scitex-dev-ecosystem managed crontab block (cron)"

#: JobSpec fields that a lowered timer carries through unchanged.
_PRESERVED_FIELDS = frozenset({"name", "command", "description"})

#: JobSpec fields the lowering deliberately re-derives. ``kind`` flips to
#: ``"cron"``; ``schedule`` becomes the derived 5-field expression, which
#: is where ``on_unit_active_sec`` is consumed (see ``derive_cron_expr``).
_TRANSLATED_FIELDS = frozenset({"kind", "schedule", "on_unit_active_sec"})

#: JobSpec fields a ``kind="timer"`` spec cannot legally set in the first
#: place (``JobSpec._validate_timer`` rejects them), so there is nothing
#: for the lowering to lose.
#:
#: The stop/lifecycle fields belong here for the same reason and NOT in
#: ``_LOSS_DETECTED_FIELDS``: they describe how a LONG-RUNNING PROCESS is
#: signalled, reloaded and prevented from restarting. A timer fires a
#: oneshot that exits on its own, so there is no daemon to send SIGINT to
#: and no restart to prevent — the lowering is not dropping a guarantee, the
#: guarantee was never expressible on this kind.
#:
#: If a future `kind="timer"` is allowed to carry one of these, it MUST move
#: to ``_LOSS_DETECTED_FIELDS`` instead, because silently lowering a declared
#: stop signal to a crontab line would drop it without a word — which is the
#: original bug this whole module exists to prevent.
#: ``service_type`` joins them on the same test, not by analogy:
#: ``_validate_timer`` refuses it outright, because a timer-triggered body
#: IS a oneshot. Nothing for the lowering to lose.
_INAPPLICABLE_TO_TIMER = frozenset(
    {
        "restart_policy",
        "watchdog_sec",
        "kill_signal",
        "kill_mode",
        "timeout_stop_sec",
        "exec_reload",
        "exec_stop",
        "restart_prevent_exit_status",
        "service_type",
    }
)

#: Fields :func:`lowering_losses` inspects and reports on.
#:
#: The unit-body fields land HERE rather than above, and the distinction is
#: the one this module exists to keep honest: a timer may legally declare
#: them, so lowering to cron genuinely DROPS something the leaf asked for.
#: ``working_directory``, ``environment`` and ``environment_file`` are
#: blocking for the same reason ``venv`` is — each decides what the command
#: actually resolves to and runs against, so losing one silently changes
#: what executes. ``remain_after_exit`` is advisory: it only shapes what
#: ``systemctl is-active`` reports, and cron has no unit to report on.
_LOSS_DETECTED_FIELDS = frozenset(
    {
        "timeout_sec",
        "on_boot_sec",
        "venv",
        "on_calendar",
        "remain_after_exit",
        "working_directory",
        "environment",
        "environment_file",
    }
)


@dataclass(frozen=True)
class DroppedProperty:
    """One declared JobSpec property the target surface cannot carry.

    Pure data — produced by :func:`lowering_losses`, rendered by
    :class:`TimerLoweringError`. ``consequence`` says what actually
    happens on the host; ``remedy`` is what the operator can DO about
    it, so the failure is actionable rather than merely loud.


    ``blocking`` separates a dropped GUARANTEE from a dropped
    PREFERENCE. Both are always reported — nothing is ever silent — but
    only a blocking loss refuses the lowering. Measured on the live
    fleet (2026-07-19): all 10 timer-kind JobSpecs drop something, yet
    only 7 drop a guarantee. Refusing on all 10 would fire the guard on
    100% of jobs and train the operator to pass the opt-in permanently,
    which is how a loud check decays back into a silent one.
    """

    field: str
    declared: object
    consequence: str
    remedy: str
    blocking: bool = True

    def describe(self) -> str:
        return (
            f"  - {self.field}={self.declared!r}: {self.consequence}\n"
            f"    Fix: {self.remedy}"
        )


class TimerLoweringError(RuntimeError):
    """A timer JobSpec declares guarantees cron cannot honour.

    Raised by :func:`timer_to_cron_jobspec` / :func:`collect_cron_jobs`
    unless the caller explicitly opts into the degraded lowering. The
    message names the JOB, the TARGET SURFACE and every PROPERTY at
    stake, because a silent downgrade under the same name is exactly
    the failure mode this guard exists to prevent.
    """

    def __init__(self, job_name: str, losses: tuple[DroppedProperty, ...]):
        self.job_name = job_name
        self.losses = losses
        super().__init__(format_loss_report(job_name, losses))


def format_loss_report(
    job_name: str, losses: tuple[DroppedProperty, ...]
) -> str:
    """Render the operator-facing REFUSAL text. Pure."""
    return (
        f"refusing to lower timer job {job_name!r} onto {TARGET_SURFACE}: "
        f"{_loss_body(job_name, losses)}\n"
        f"Deploying anyway would install a WEAKER artifact under the SAME "
        f"name — the registry would keep a promise the host cannot honour.\n"
        f"To accept the degradation explicitly, rerun with "
        f"--allow-lossy-timer-lowering; every degraded job is then "
        f"reported by name."
    )


def format_degraded_report(
    job_name: str, losses: tuple[DroppedProperty, ...]
) -> str:
    """Render the text for a loss the caller has explicitly accepted. Pure.

    Same facts as :func:`format_loss_report`, but phrased for what is
    actually happening — the job IS being deployed, weaker than declared
    — rather than for a refusal that did not occur.
    """
    return (
        f"lowering timer job {job_name!r} onto {TARGET_SURFACE} ANYWAY: "
        f"{_loss_body(job_name, losses)}\n"
        f"This job is now deployed WEAKER than its JobSpec declares. The "
        f"registry promise is not honoured on the host."
    )


def _loss_body(job_name: str, losses: tuple[DroppedProperty, ...]) -> str:
    plural = "property" if len(losses) == 1 else "properties"
    body = "\n".join(loss.describe() for loss in losses)
    return f"cron cannot carry {len(losses)} declared {plural}.\n{body}"


def lowering_losses(job: JobSpec) -> tuple[DroppedProperty, ...]:
    """Return the declared properties lost when ``job`` lowers to cron.

    Pure function over a JobSpec — no I/O, no crontab, no systemd. This
    is the testable core of the guarantee-dropping guard.

    Returns an empty tuple for a timer that loses nothing (and for any
    non-timer job, which does not go through the lowering at all).
    """
    if job.kind != "timer":
        return ()

    losses: list[DroppedProperty] = []

    if job.on_calendar:
        losses.append(
            DroppedProperty(
                field="on_calendar",
                declared=job.on_calendar,
                consequence=(
                    "a crontab line carries no timezone — it fires in the "
                    "cron daemon's own TZ. An OnCalendar naming a zone "
                    "(`*-*-* 04:30:00 Asia/Tokyo`) would silently become "
                    "04:30 in whatever zone the host happens to run, which "
                    "is a DIFFERENT time on every host that disagrees, and "
                    "moves twice a year wherever DST applies"
                ),
                remedy=(
                    "keep the job as kind='timer' so systemd honours the "
                    "zone, or restate the schedule as a plain 5-field cron "
                    "expression in `schedule` and accept host-local time "
                    "explicitly rather than by accident"
                ),
            )
        )

    if job.timeout_sec is not None:
        losses.append(
            DroppedProperty(
                field="timeout_sec",
                declared=job.timeout_sec,
                consequence=(
                    "a cron line has no timeout; the job would deploy "
                    "UNBOUNDED, so a run that outlives its own cadence "
                    "piles up against the next one instead of being killed"
                ),
                remedy=(
                    "make the command self-bounding (its own --timeout, or "
                    "a `timeout` in the JobSpec.command itself), or drop "
                    "timeout_sec from the JobSpec to state honestly that "
                    "the run is unbounded"
                ),
            )
        )

    if job.on_boot_sec is not None:
        losses.append(
            DroppedProperty(
                field="on_boot_sec",
                declared=job.on_boot_sec,
                consequence=(
                    "cron has no boot concept, so the declared post-boot "
                    "start delay is not applied — the job simply fires on "
                    "the next matching wall-clock slot"
                ),
                remedy=(
                    "drop on_boot_sec (harmless for a periodic job whose "
                    "cadence already spreads it out), or fold the delay "
                    "into the command if the startup ordering is real"
                ),
                # Advisory: a start-delay preference, not a guarantee. An
                # unapplied delay makes a job fire EARLIER than asked; it
                # cannot pile up runs or leave one unbounded.
                blocking=False,
            )
        )

    if job.venv is not None:
        losses.append(
            DroppedProperty(
                field="venv",
                declared=job.venv,
                consequence=(
                    "the cron line runs job.command verbatim on cron's "
                    "minimal PATH; the leaf-owned venv is NOT used, so the "
                    "command may resolve to a different interpreter, a "
                    "stale binary, or nothing at all"
                ),
                remedy=(
                    "write an absolute <venv>/bin/<exe> path into "
                    "JobSpec.command so the resolution is explicit, or "
                    "keep the job off cron until the timer surface lands"
                ),
            )
        )

    if job.working_directory is not None:
        losses.append(
            DroppedProperty(
                field="working_directory",
                declared=job.working_directory,
                consequence=(
                    "cron runs the command from the crontab owner's home "
                    "directory, not the declared one, so every relative path "
                    "in the command resolves somewhere else — silently, and "
                    "possibly onto real files"
                ),
                remedy=(
                    "make the command absolute, or prefix it with an "
                    "explicit `cd <dir> && `, so the directory travels with "
                    "the command instead of with the unit"
                ),
            )
        )

    if job.environment_file is not None:
        losses.append(
            DroppedProperty(
                field="environment_file",
                declared=job.environment_file,
                consequence=(
                    "cron has no EnvironmentFile, so the command runs "
                    "WITHOUT the configuration and secrets that file "
                    "carries — usually the only on-disk record of where "
                    "they come from — and the failure surfaces as wrong "
                    "behaviour rather than a missing-file error"
                ),
                remedy=(
                    "source the file inside JobSpec.command "
                    "(`set -a; . <file>; set +a; <cmd>`), or keep the job "
                    "on the timer surface where the unit can carry it"
                ),
            )
        )

    if job.environment:
        losses.append(
            DroppedProperty(
                field="environment",
                declared=", ".join(job.environment),
                consequence=(
                    "cron does not carry Environment= entries, so the "
                    "command runs on cron's minimal environment and any "
                    "variable it depends on is simply absent"
                ),
                remedy=(
                    "inline the assignments into JobSpec.command "
                    "(`KEY=value <cmd>`), or keep the job on the timer "
                    "surface"
                ),
            )
        )

    if job.remain_after_exit is not None:
        losses.append(
            DroppedProperty(
                field="remain_after_exit",
                declared=str(job.remain_after_exit),
                consequence=(
                    "cron has no unit whose activeness could be reported, "
                    "so the declared post-exit state is meaningless there"
                ),
                remedy=(
                    "drop remain_after_exit for the cron surface — it "
                    "shapes `systemctl is-active` output only, and nothing "
                    "reads that for a crontab line"
                ),
                # Advisory: it changes what STATUS reports, never what runs.
                # It cannot pile up runs or leave one unbounded.
                blocking=False,
            )
        )

    return tuple(losses)


def blocking_losses(job: JobSpec) -> tuple[DroppedProperty, ...]:
    """Losses that REFUSE the lowering — dropped guarantees. Pure."""
    return tuple(loss for loss in lowering_losses(job) if loss.blocking)


def advisory_losses(job: JobSpec) -> tuple[DroppedProperty, ...]:
    """Losses that are reported but do not refuse — preferences. Pure."""
    return tuple(loss for loss in lowering_losses(job) if not loss.blocking)


def accounted_fields() -> frozenset[str]:
    """Every JobSpec field this module has an explicit position on.

    Guard-railed by a test: if a new field is added to JobSpec and not
    classified here (preserved / translated / inapplicable / loss-
    detected), the test fails rather than the field being silently
    dropped by the lowering — the precise bug this module fixes.
    """
    return (
        _PRESERVED_FIELDS
        | _TRANSLATED_FIELDS
        | _INAPPLICABLE_TO_TIMER
        | _LOSS_DETECTED_FIELDS
    )


def jobspec_field_names() -> frozenset[str]:
    """Names of every field on the JobSpec dataclass. Pure."""
    return frozenset(f.name for f in fields(JobSpec))


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
        command=job.command,
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
    """
    cron_native = [j for j in jobs if j.kind == "cron"]
    timer_jobs = [j for j in jobs if j.kind == "timer"]

    lowered: list[JobSpec] = []
    for timer in timer_jobs:
        if on_degrade is not None:
            _report(timer, allow_lossy=allow_lossy, on_degrade=on_degrade)
        lowered.append(timer_to_cron_jobspec(timer, allow_lossy=allow_lossy))

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
    "degraded_job_names",
    "derive_cron_expr",
    "format_degraded_report",
    "format_loss_report",
    "jobspec_field_names",
    "lowering_losses",
    "timer_to_cron_jobspec",
]


# EOF
