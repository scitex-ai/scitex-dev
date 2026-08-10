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
    "periodic": "timer, or 'cron' when schedule is set",
}

#: Valid ``JobSpec.restart_policy`` values. Used by the ``service`` kind
#: only; ignored (and required to be ``"no"``) by ``timer`` / ``cron``.
ALLOWED_RESTART_POLICIES: frozenset[str] = frozenset(
    {"no", "on-failure", "on-abnormal", "on-abort", "on-watchdog", "always"}
)


def canonical_kind(kind: str, schedule: str) -> str:
    """Map an INTENT spelling onto its stored kind. Identity otherwise.

    ``periodic`` resolves by a field that already exists rather than by a
    new one: a ``schedule`` means crontab, its absence means a systemd
    timer. That mirrors the existing semantics exactly — ``cron`` uses
    ``schedule``, ``timer`` uses ``on_unit_active_sec`` — instead of
    inventing a second way to express the same choice, which would then be
    able to disagree with the first.

    Unknown values pass through unchanged so the caller's validator can
    reject them with its own message, naming the field and the valid set.
    Swallowing them here would move the error away from where it is
    explained.
    """
    if kind == "daemon":
        return "service"
    if kind == "periodic":
        return "cron" if schedule else "timer"
    return kind

# EOF
