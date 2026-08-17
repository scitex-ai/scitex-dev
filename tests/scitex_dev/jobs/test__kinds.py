#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The INTENT spellings, and the promise that adding them broke nothing.

``daemon`` / ``periodic`` name what a job DOES; ``service`` / ``timer`` /
``cron`` are what gets stored, and ``timer`` vs ``cron`` differ only by
scheduler. The new names are normalised at construction, so every consumer
comparing ``job.kind == "service"`` is untouched.

Half of this suite therefore tests that NOTHING CHANGED. That is the point:
the enum is a federated contract — sac declares 7 JobSpecs, the built-ins 11
— and the whole reason to normalise rather than rename is that a flag-day
rename breaks all of them at once. A test that only covered the new
spellings would not notice if the old ones had stopped working.
"""

from __future__ import annotations

from typing import Any, Callable

from scitex_dev.jobs import (
    ACCEPTED_KINDS,
    ALLOWED_KINDS,
    INTENT_KINDS,
    JobSpec,
    canonical_kind,
)


def _error_from(call: Callable[[], Any]) -> "BaseException | None":
    """Run ``call`` and hand back what it raised, so each test asserts once."""
    try:
        call()
    except BaseException as exc:  # noqa: BLE001 - capturing any is the point
        return exc
    return None


def _spec(**over) -> JobSpec:
    """A minimal valid JobSpec. Every field is explicit — the dataclass has
    no defaults for `schedule` / `description`, deliberately, so a provider
    cannot omit them by accident."""
    base = dict(
        name="pkg.job",
        kind="service",
        schedule="",
        command="/bin/true",
        description="fixture job",
    )
    base.update(over)
    return JobSpec(**base)


# -- the mapping, as a pure function --------------------------------------
def test_daemon_maps_to_service():
    # Arrange
    expected = "service"
    # Act
    got = canonical_kind("daemon", "")
    # Assert
    assert got == expected


def test_periodic_without_a_schedule_maps_to_timer():
    # Arrange
    expected = "timer"
    # Act
    got = canonical_kind("periodic", "")
    # Assert
    assert got == expected


def test_periodic_with_a_schedule_is_refused_as_ambiguous():
    # Arrange -- a schedule does NOT identify the scheduler: a systemd timer
    # may carry one as an OnCalendar fallback, and live sac declarations do.
    schedule = "*/5 * * * *"
    # Act
    err = _error_from(lambda: canonical_kind("periodic", schedule))
    # Assert
    assert isinstance(err, ValueError)


def test_the_refusal_names_both_explicit_kinds_so_the_fix_is_obvious():
    # Arrange -- an error that says "ambiguous" without saying what to write
    # instead leaves the declarer guessing between the two candidates.
    schedule = "*/5 * * * *"
    # Act
    err = _error_from(lambda: canonical_kind("periodic", schedule))
    # Assert
    assert "'cron'" in str(err) and "'timer'" in str(err)


def test_a_jobspec_cannot_smuggle_the_ambiguous_pair_past_construction():
    # Arrange -- the guard must hold at the dataclass, not only in the helper,
    # because providers construct JobSpecs and never call canonical_kind.
    # Act
    err = _error_from(lambda: _spec(kind="periodic", schedule="*/5 * * * *"))
    # Assert
    assert isinstance(err, ValueError)


def test_a_stored_kind_passes_through_unchanged():
    # Arrange
    stored = "timer"
    # Act
    got = canonical_kind(stored, "")
    # Assert
    assert got == stored


def test_an_unknown_kind_passes_through_for_the_validator_to_reject():
    # Arrange — swallowing it here would move the error away from its message
    unknown = "nonsense"
    # Act
    got = canonical_kind(unknown, "")
    # Assert
    assert got == unknown


# -- normalisation through the dataclass ----------------------------------
def test_a_daemon_spec_stores_kind_service():
    # Arrange
    spec = _spec(kind="daemon")
    # Act
    stored = spec.kind
    # Assert
    assert stored == "service"


def test_a_periodic_spec_stores_kind_timer():
    # Arrange
    spec = _spec(kind="periodic", on_unit_active_sec=300)
    # Act
    stored = spec.kind
    # Assert
    assert stored == "timer"


def test_the_explicit_cron_escape_from_the_refusal_works():
    # Arrange -- the refusal tells the declarer to say 'cron' or 'timer'. An
    # error naming a remedy nobody tested is how a fix instruction goes stale.
    spec = _spec(kind="cron", schedule="*/5 * * * *")
    # Act
    stored = spec.kind
    # Assert
    assert stored == "cron"


def test_the_explicit_timer_escape_from_the_refusal_works():
    # Arrange -- the case that made the inference unsound: a systemd timer
    # legally carrying a schedule, as seven live sac declarations do.
    spec = _spec(kind="timer", schedule="*/5 * * * *")
    # Act
    stored = spec.kind
    # Assert
    assert stored == "timer"


def test_intent_reads_daemon_for_a_service():
    # Arrange
    spec = _spec(kind="service")
    # Act
    intent = spec.intent
    # Assert
    assert intent == "daemon"


def test_intent_reads_periodic_for_a_timer():
    # Arrange
    spec = _spec(kind="timer", on_unit_active_sec=300)
    # Act
    intent = spec.intent
    # Assert
    assert intent == "periodic"


def test_intent_reads_periodic_for_a_cron():
    # Arrange
    spec = _spec(kind="cron", schedule="*/5 * * * *")
    # Act
    intent = spec.intent
    # Assert
    assert intent == "periodic"


# -- nothing broke --------------------------------------------------------
def test_the_stored_vocabulary_is_unchanged():
    # Arrange — a federated contract; this set is what providers rely on
    expected = {"service", "timer", "cron"}
    # Act
    got = set(ALLOWED_KINDS)
    # Assert
    assert got == expected


def test_accepted_kinds_is_the_union_of_both_vocabularies():
    # Arrange
    expected = set(ALLOWED_KINDS) | set(INTENT_KINDS)
    # Act
    got = set(ACCEPTED_KINDS)
    # Assert
    assert got == expected


def test_a_plain_service_spec_still_constructs():
    # Arrange
    spec = _spec(kind="service")
    # Act
    stored = spec.kind
    # Assert
    assert stored == "service"


def test_a_plain_cron_spec_still_constructs():
    # Arrange
    spec = _spec(kind="cron", schedule="*/5 * * * *")
    # Act
    stored = spec.kind
    # Assert
    assert stored == "cron"


def test_an_invalid_kind_still_raises():
    # Arrange
    bad = "nonsense"
    # Act
    caught = _error_from(lambda: _spec(kind=bad))
    # Assert
    assert isinstance(caught, ValueError)


def test_the_rejection_message_names_the_intent_spellings():
    # Arrange
    bad = "nonsense"
    # Act
    caught = _error_from(lambda: _spec(kind=bad))
    # Assert
    assert "daemon" in str(caught)

# EOF
