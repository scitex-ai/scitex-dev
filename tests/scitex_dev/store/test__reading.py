#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Three-valued reads: true / false / UNKNOWN, never collapsed.

The distinction under test is the one a bare ``None`` return destroys --
"there is no such record" versus "I have not heard from the host that
would know". Single-writer-per-record makes it decidable rather than
vague, and these tests pin both halves of that asymmetry: silence from a
record's OWNER makes a positive read uncertain, while silence from anyone
makes a negative read uncertain.

Pure functions only -- no database, no clock, no mocks: ``now`` is passed
in as a number.
"""

from __future__ import annotations

from scitex_dev.store._reading import (
    HostSilence,
    Reading,
    Watermark,
    describe_duration,
    silences_from,
)

NOW = 1_000_000_000.0
FRESH = "2001-09-09T01:46:40+00:00"  # exactly NOW, in UTC
OLD = "2001-09-08T21:46:40+00:00"  # exactly 4h (14400s) before NOW


def _silence(origin="beta", seconds=14400.0):
    return HostSilence(origin, OLD, seconds)


# --- duration rendering ----------------------------------------------------


def test_duration_renders_hours_for_long_silences():
    # Arrange
    seconds = 4 * 3600
    # Act
    rendered = describe_duration(seconds)
    # Assert
    assert rendered == "4h"


def test_duration_renders_minutes_for_medium_silences():
    # Arrange
    seconds = 900
    # Act
    rendered = describe_duration(seconds)
    # Assert
    assert rendered == "15m"


def test_duration_renders_seconds_for_short_silences():
    # Arrange
    seconds = 30
    # Act
    rendered = describe_duration(seconds)
    # Assert
    assert rendered == "30s"


# --- who counts as silent --------------------------------------------------


def test_recently_heard_host_is_not_silent():
    # Arrange
    heard = [("beta", FRESH)]
    # Act
    silences = silences_from(heard, NOW, 900.0)
    # Assert
    assert silences == ()


def test_long_quiet_host_is_reported_silent():
    # Arrange
    heard = [("beta", OLD)]
    # Act
    silences = silences_from(heard, NOW, 900.0)
    # Assert
    assert silences[0].origin == "beta"


def test_unparseable_stamp_counts_as_silent_forever():
    """A broken clock must never be read as "recently heard"."""
    # Arrange
    heard = [("beta", "not-a-timestamp")]
    # Act
    silences = silences_from(heard, NOW, 900.0)
    # Assert
    assert silences[0].silent_seconds == float("inf")


def test_missing_stamp_counts_as_silent():
    # Arrange
    heard = [("beta", "")]
    # Act
    silences = silences_from(heard, NOW, 900.0)
    # Assert
    assert silences[0].origin == "beta"


# --- the three values ------------------------------------------------------


def test_found_record_with_every_host_heard_is_true():
    # Arrange
    reading = Reading(found=True, payload="x", owner="alpha")
    # Act
    value = reading.value
    # Assert
    assert value is True


def test_missing_record_with_every_host_heard_is_false():
    # Arrange
    reading = Reading(found=False)
    # Act
    value = reading.value
    # Assert
    assert value is False


def test_missing_record_with_a_silent_host_is_unknown():
    """The whole point: absence plus silence is UNKNOWN, never "no"."""
    # Arrange
    reading = Reading(found=False, unheard=(_silence(),))
    # Act
    value = reading.value
    # Assert
    assert value is None


def test_found_record_whose_owner_is_silent_is_unknown():
    # Arrange
    reading = Reading(found=True, payload="x", owner="beta", unheard=(_silence(),))
    # Act
    value = reading.value
    # Assert
    assert value is None


def test_found_record_survives_silence_from_a_non_owner():
    """Only the OWNER can have changed it, so another host's silence is moot."""
    # Arrange
    reading = Reading(found=True, payload="x", owner="alpha", unheard=(_silence(),))
    # Act
    value = reading.value
    # Assert
    assert value is True


def test_unknown_reading_reports_itself_uncertain():
    # Arrange
    reading = Reading(found=False, unheard=(_silence(),))
    # Act
    certain = reading.is_certain
    # Assert
    assert certain is False


# --- the answer describes itself -------------------------------------------


def test_absent_reading_describes_the_watermark_and_the_silence():
    # Arrange
    reading = Reading(
        found=False,
        watermark=Watermark((("alpha", 7), ("beta", 3))),
        unheard=(_silence(),),
    )
    # Act
    described = reading.describe()
    # Assert
    assert described == (
        "none, as of watermark {alpha:7, beta:3}, with host beta unheard-from for 4h"
    )


def test_certain_absence_still_names_its_watermark():
    # Arrange
    reading = Reading(found=False, watermark=Watermark((("alpha", 7),)))
    # Act
    described = reading.describe()
    # Assert
    assert described == "none, as of watermark {alpha:7}"


def test_reading_dict_carries_the_three_valued_answer():
    # Arrange
    reading = Reading(found=False, unheard=(_silence(),))
    # Act
    payload = reading.to_dict()
    # Assert
    assert payload["unknown"] is True


def test_watermark_reports_a_missing_origin_as_zero():
    # Arrange
    watermark = Watermark((("alpha", 7),))
    # Act
    seq = watermark.seq_for("gamma")
    # Assert
    assert seq == 0


# EOF
