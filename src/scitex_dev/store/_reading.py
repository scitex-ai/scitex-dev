#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reads that carry their own uncertainty. Never a bare "none".

A replica can only answer from what has reached it. "No such record"
therefore means one of two very different things -- *there is no such
record* or *I have not heard from the host that would know* -- and a
result type that cannot tell them apart forces every caller to guess.
So the answer here is three-valued throughout (true / false / UNKNOWN)
and it is never collapsed: :attr:`Reading.value` returns ``None`` for
UNKNOWN, and :meth:`Reading.describe` renders the whole answer, e.g.

    none, as of watermark {alpha:7, beta:3}, with host beta unheard-from for 4h

Single-writer-per-record is what makes the distinction sharp rather than
vague. Exactly one origin may write a given record, so:

* the record was FOUND -- only its OWNER can have changed it since, so
  silence from any OTHER host is irrelevant and the answer stays certain;
* the record was NOT found -- any silent host could be the owner that
  created it, so the answer is UNKNOWN until every host is heard from.

That asymmetry is the point. It keeps "not found" honest without making
every read pessimistic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

__all__ = [
    "DEFAULT_SILENCE_THRESHOLD_S",
    "HostSilence",
    "Reading",
    "Watermark",
    "describe_duration",
    "silences_from",
]

#: A host quieter than this is reported in every read it could affect.
#: It is a REPORTING threshold, never a timeout: nothing is evicted,
#: nothing is assumed dead, and no record is deleted because a host went
#: quiet. Silence only ever downgrades certainty.
DEFAULT_SILENCE_THRESHOLD_S = 900.0


def describe_duration(seconds: float) -> str:
    """Human-scale duration: ``4h``, ``15m``, ``30s``."""
    if seconds >= 3600:
        return "{0:.0f}h".format(seconds / 3600)
    if seconds >= 60:
        return "{0:.0f}m".format(seconds / 60)
    return "{0:.0f}s".format(max(seconds, 0))


@dataclass(frozen=True)
class HostSilence:
    """One host we have not heard from recently, and for how long."""

    origin: str
    last_heard_at: str
    silent_seconds: float

    def describe(self) -> str:
        return "host {0} unheard-from for {1}".format(
            self.origin, describe_duration(self.silent_seconds)
        )


@dataclass(frozen=True)
class Watermark:
    """How far this replica has consumed each origin's log."""

    cursors: tuple = ()

    def describe(self) -> str:
        if not self.cursors:
            return "{}"
        body = ", ".join(
            "{0}:{1}".format(origin, seq) for origin, seq in sorted(self.cursors)
        )
        return "{" + body + "}"

    def seq_for(self, origin: str) -> int:
        for name, seq in self.cursors:
            if name == origin:
                return int(seq)
        return 0


@dataclass(frozen=True)
class Reading:
    """The answer to one lookup, WITH the uncertainty that produced it."""

    found: bool
    payload: str = ""
    owner: str = ""
    watermark: Watermark = Watermark()
    unheard: tuple = ()

    @property
    def owner_is_silent(self) -> bool:
        return any(silence.origin == self.owner for silence in self.unheard)

    @property
    def value(self):
        """Three-valued: ``True`` / ``False`` / ``None`` for UNKNOWN.

        Never collapsed to a bool. A caller that wants to treat UNKNOWN as
        one or the other must say so at its own call site, where the
        consequence of being wrong is visible.
        """
        if self.found:
            return None if self.owner_is_silent else True
        return None if self.unheard else False

    @property
    def is_unknown(self) -> bool:
        return self.value is None

    @property
    def is_certain(self) -> bool:
        return self.value is not None

    def describe(self) -> str:
        head = "found" if self.found else "none"
        parts = [head, "as of watermark {0}".format(self.watermark.describe())]
        if self.unheard:
            parts.append(
                "with " + ", ".join(silence.describe() for silence in self.unheard)
            )
        return ", ".join(parts)

    def to_dict(self) -> dict:
        return {
            "found": self.found,
            "value": self.value,
            "unknown": self.is_unknown,
            "owner": self.owner,
            "payload": self.payload,
            "watermark": dict(self.watermark.cursors),
            "unheard": [
                {
                    "origin": silence.origin,
                    "last_heard_at": silence.last_heard_at,
                    "silent_seconds": silence.silent_seconds,
                }
                for silence in self.unheard
            ],
            "describe": self.describe(),
        }


def _parse(stamp: str):
    try:
        parsed = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def silences_from(
    heard,
    now: float,
    threshold_seconds: float = DEFAULT_SILENCE_THRESHOLD_S,
) -> tuple:
    """Which of ``heard`` -- ``(origin, last_heard_at)`` pairs -- are quiet.

    An UNPARSEABLE or empty stamp counts as silent since forever rather
    than as fresh. Reading a broken clock as "recently heard" would
    manufacture certainty out of a bug, which is the failure mode this
    whole module exists to prevent.
    """
    out = []
    for origin, last_heard_at in heard:
        parsed = _parse(last_heard_at or "")
        if parsed is None:
            out.append(HostSilence(origin, last_heard_at or "", float("inf")))
            continue
        silent = now - parsed.timestamp()
        if silent >= threshold_seconds:
            out.append(HostSilence(origin, last_heard_at, silent))
    return tuple(sorted(out, key=lambda silence: silence.origin))


# EOF
