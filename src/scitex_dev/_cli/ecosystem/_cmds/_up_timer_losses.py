#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What a lowered timer JobSpec LOSES on the crontab surface. Pure.

Split out of ``_up_timer_lowering.py`` (which held both this and the
cron-expression translation, and outgrew the line cap). This half owns
one question and answers it without I/O: *which declared properties can
this surface not carry, and how bad is each?*

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

Carried, not merely refused
---------------------------
``timeout_sec`` is no longer dropped at all in the ordinary case: the
lowering materialises it as a ``timeout <N> `` prefix on the cron line
(:func:`cron_command_for`), so the bound is declared ONCE on the JobSpec
and each rail expresses it natively — ``TimeoutStartSec=`` on a systemd
unit, a ``timeout`` prefix on a crontab line. It reverts to a blocking
loss only for a compound command, where the prefix would bind just the
first stage.

The tempting alternative — asking each leaf to put ``timeout 120 ...``
in ``JobSpec.command`` — is WRONG and was nearly shipped. ``resolve_
execstart`` absolutises only the head token, so that command renders as
``ExecStart=/usr/bin/timeout 120 sac ...`` with ``sac`` still relative
under systemd's minimal PATH: exit 127, and the loud unresolvable-head
warning never fires because the head resolved. Ten working timers would
have become silent crash-loopers. Caught by sac, 2026-08-19.

Two tiers, both reported, only one blocking:

* **blocking** (``venv``, and ``timeout_sec`` for a compound command) —
  a dropped guarantee. The deployed artifact is genuinely weaker than
  the registry claims, so the reconcile refuses THAT JOB.
* **advisory** (``on_boot_sec``) — a dropped preference. Echoed on
  every run, never blocking. Measured on the live fleet 2026-07-19,
  ALL 10 timer JobSpecs drop something but only 7 drop a guarantee;
  refusing on all 10 would make the opt-in flag permanent, which is
  how a loud check decays back into a silent one.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

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
#: ``timeout_sec`` stays here even though the lowering now CARRIES it as a
#: ``timeout <N> `` prefix: it is still INSPECTED, and it is still lost in
#: the one case the prefix cannot express (a compound command). Listing it
#: as translated would claim it always survives, which is the kind of
#: half-true classification this table exists to prevent.
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


#: Shell operators that make a command unsafe to prefix with ``timeout``.
#:
#: ``timeout 120 a && b`` runs ``b`` UNBOUNDED — the shell binds ``&&``
#: after ``timeout`` has already taken its argv. Same for ``;``, ``|``
#: and redirections. Substitutions (``$(...)``, backticks) are included
#: because what they expand to is not knowable at render time, so the
#: wrap cannot be shown to bind the real command.
_SHELL_OPERATORS = ("&&", "||", "|", ";", "&", ">", "<", "$", "`", "\n")


def command_is_wrappable(command: str) -> bool:
    """True when ``timeout <N> `` can be prefixed without changing meaning.

    Pure. The cron rail materialises :attr:`JobSpec.timeout_sec` as a
    ``timeout`` prefix, which is faithful for a plain ``argv``-shaped
    command and a LIE for a compound one: the bound would cover only
    the first stage while the crontab line still carries the job's name
    and its declared timeout.

    Deploying a job that looks bounded and is not is strictly worse
    than refusing it, which is why this returns False rather than
    trying to be clever with quoting — an ``sh -c`` wrap would work but
    needs `%`-escaping for crontab and careful requoting, and no job in
    the fleet needs it today (measured 2026-08-19: 0 of 10).
    """
    return not any(op in command for op in _SHELL_OPERATORS)


def cron_command_for(job: JobSpec) -> str:
    """Render ``job``'s command for a cron line, carrying the bound. Pure.

    This is where ``timeout_sec`` survives the trip to cron. It is
    deliberately NOT done by rewriting ``JobSpec.command`` upstream:
    ``resolve_execstart`` absolutises only the HEAD token, so a
    ``timeout 120 sac ...`` command would render the systemd unit as
    ``/usr/bin/timeout 120 sac ...`` with ``sac`` left relative under
    systemd's minimal PATH — exit 127, and the loud unresolvable-head
    warning would not fire because the head resolved fine. Credit to
    sac for catching that before it shipped (2026-08-19).

    The cron rail has no such hazard: ``build_cron_line`` interpolates
    the command verbatim and the synthetic cron JobSpec reaches no
    ``resolve_execstart`` caller, so the prefix binds exactly what it
    appears to bind.
    """
    if job.timeout_sec is None or not command_is_wrappable(job.command):
        return job.command
    return f"timeout {job.timeout_sec} {job.command}"


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

    if job.timeout_sec is not None and not command_is_wrappable(job.command):
        losses.append(
            DroppedProperty(
                field="timeout_sec",
                declared=job.timeout_sec,
                consequence=(
                    "the lowering normally carries timeout_sec as a "
                    "`timeout <N> ` prefix on the cron line, but this "
                    "command contains a shell operator, and `timeout N a "
                    "&& b` bounds only `a` — so the wrap would deploy a "
                    "job that LOOKS bounded and is not, which is worse "
                    "than one honestly reported as unbounded"
                ),
                remedy=(
                    "split the compound command into separate JobSpecs "
                    "(each then gets its own honest bound), or move the "
                    "shell logic into a script and point command at that "
                    "script, or drop timeout_sec to state honestly that "
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


__all__ = [
    "TARGET_SURFACE",
    "DroppedProperty",
    "TimerLoweringError",
    "accounted_fields",
    "advisory_losses",
    "blocking_losses",
    "format_degraded_report",
    "format_loss_report",
    "jobspec_field_names",
    "lowering_losses",
]
