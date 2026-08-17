#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The job-kind taxonomy — what kinds exist, and how a spelling maps to one.

Extracted from ``jobs/__init__.py`` because it is a FEDERATED contract, not
an implementation detail of :class:`~scitex_dev.jobs.JobSpec`. sac declares
7 JobSpecs, the built-ins 11, plus any other provider registered under the
``scitex_dev.jobs`` entry-point group — all of them reason about these
values without touching the dataclass. A contract that many packages read
should be legible on its own.

Two vocabularies, and the reason there are two
----------------------------------------------
The original three kinds mix two axes, which is exactly why the names have
always felt slightly wrong:

    service   INTENT (runs continuously) — already mechanism-agnostic: a
              systemd unit, or the respawn keep-alive loop used on hosts
              without `systemd --user`
    timer     MECHANISM (systemd .timer)  for the intent "run periodically"
    cron      MECHANISM (crontab)         for the intent "run periodically"

So ``timer`` and ``cron`` are the SAME intent with the scheduler baked into
the type name, while ``service`` is mechanism-free. Mixed levels of
abstraction in one enum.

The intent-level names are ``daemon`` and ``periodic``. They are accepted on
input and normalised to the stored values by :func:`canonical_kind`, which
is the ONLY place the two vocabularies meet.

One combination is REFUSED rather than normalised: ``periodic`` together
with a ``schedule``. The intent vocabulary names what a job does but not
which scheduler runs it, and with no ``mechanism`` field to read there is
nothing that can decide it — ``schedule`` cannot, because a systemd timer
may legally carry one too. See :func:`canonical_kind` for the full
reasoning and the live declarations that prove the point.

Why normalise instead of rename
-------------------------------
Renaming the enum would break every provider at once. Normalising is purely
additive: nothing downstream changes, every ``job.kind == "service"``
comparison keeps working, and providers migrate at their own pace or never.

Dropping the old spellings is the breaking half and is NOT done here — that
part needs a ruling, because its blast radius is other packages' code. See
card ``dev-jobspec-kind-taxonomy-intent-vs-mechanism-20260719``.
"""

from __future__ import annotations

__all__ = [
    "ACCEPTED_KINDS",
    "ALLOWED_KINDS",
    "ALLOWED_RESTART_POLICIES",
    "INTENT_KINDS",
    "INTENT_TO_KIND",
    "canonical_kind",
]

#: Valid stored ``JobSpec.kind`` values. What every consumer compares against.
ALLOWED_KINDS: frozenset[str] = frozenset({"service", "timer", "cron"})

#: INTENT spellings accepted on input and normalised into
#: :data:`ALLOWED_KINDS`.
INTENT_KINDS: frozenset[str] = frozenset({"daemon", "periodic"})

#: Every spelling ``JobSpec.kind`` accepts at construction.
ACCEPTED_KINDS: frozenset[str] = ALLOWED_KINDS | INTENT_KINDS

#: How each intent resolves — for documentation and error messages.
INTENT_TO_KIND: dict[str, str] = {
    "daemon": "service",
    "periodic": "timer (with a schedule, say 'cron' or 'timer' explicitly)",
}

#: Valid ``JobSpec.restart_policy`` values. Used by the ``service`` kind
#: only; ignored (and required to be ``"no"``) by ``timer`` / ``cron``.
ALLOWED_RESTART_POLICIES: frozenset[str] = frozenset(
    {"no", "on-failure", "on-abnormal", "on-abort", "on-watchdog", "always"}
)

#: Valid ``JobSpec.service_type`` values — systemd's ``Type=`` vocabulary.
#: Used by the ``service`` kind only; ``timer`` jobs are always
#: ``Type=oneshot`` (that is what a timer-triggered unit IS) and ``cron``
#: has no systemd unit at all.
#:
#: Listed because the renderer previously CHOSE the type itself, picking
#: ``simple`` or ``notify`` from whether a watchdog was requested. A
#: hand-written unit declaring anything else — ``scitex-cards-pg`` declares
#: ``Type=exec`` — could not be adopted without silently becoming
#: ``Type=simple``, which changes when systemd considers the unit started.
ALLOWED_SERVICE_TYPES: frozenset[str] = frozenset(
    {"simple", "exec", "forking", "oneshot", "dbus", "notify", "idle"}
)


def canonical_kind(kind: str, schedule: str) -> str:
    """Map an INTENT spelling onto its stored kind. Identity otherwise.

    ``periodic`` names the intent but not the scheduler, so the mechanism
    has to come from somewhere. With no ``mechanism`` field to read, this
    function can only INFER it — and for one legal combination the
    inference is unsound, so that combination is refused instead of
    guessed.

    Why ``schedule`` cannot decide it
    ---------------------------------
    The original rule was "a ``schedule`` means crontab, its absence means
    a systemd timer", justified as mirroring existing semantics: ``cron``
    uses ``schedule``, ``timer`` uses ``on_unit_active_sec``. That premise
    is false. ``schedule`` is documented on :class:`~scitex_dev.jobs.JobSpec`
    as an optional OnCalendar fallback for ``kind="timer"``, and live
    declarations use it that way — seven of sac's production jobs are
    ``kind="timer"`` carrying a 5-field cron expression.

    So ``periodic`` + ``schedule`` had TWO honest readings, and the
    inference silently picked one: a declaration rewritten from
    ``kind="timer"`` to the intent spelling would move from systemd to
    crontab with no error at construction or at ensure time. A different
    scheduler, a different environment, and nothing to notice it.

    ``periodic`` WITHOUT a schedule stays unambiguous and is unaffected.

    Why refusing costs nothing
    --------------------------
    A census on 2026-08-17 found 98 ``JobSpec`` declarations across five
    packages and ZERO using the intent spellings, so no existing caller can
    be broken. This closes the trap before the migration that would spring
    it — a mechanical "use the intent word" sweep is exactly what would
    have hit those seven jobs first.

    The real fix is the ``mechanism`` field this vocabulary shipped
    without; until it exists, the mechanism is stated by choosing the
    explicit kind. See card
    ``dev-jobspec-kind-taxonomy-intent-vs-mechanism-20260719``.

    Unknown values pass through unchanged so the caller's validator can
    reject them with its own message, naming the field and the valid set.
    Swallowing them here would move the error away from where it is
    explained. The ambiguous ``periodic`` case is the one exception, and
    only because it cannot be deferred: by the time the caller's validator
    runs, ``kind`` has already been normalised and the fact that the
    caller wrote ``periodic`` is gone. This is the last place that knows.
    """
    if kind == "daemon":
        return "service"
    if kind == "periodic":
        if schedule:
            raise ValueError(
                f"kind='periodic' with schedule={schedule!r} is ambiguous: "
                f"a schedule does not identify the scheduler, because a "
                f"systemd timer may also carry one as an OnCalendar "
                f"fallback. Say which you mean — kind='cron' for a crontab "
                f"line, or kind='timer' for a systemd timer. ('periodic' "
                f"without a schedule is unambiguous and still accepted.)"
            )
        return "timer"
    return kind

# EOF
