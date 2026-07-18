#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/versioning/_model.py

"""The version-currency verdict model — three states, and UNKNOWN is not "fine".

This is the generic core of the primitive every scitex leaf consumes to
answer one honest question: *is the code I am actually running current?*

It was extracted from scitex-agent-container's ``_freshness._model`` (PR
#677, reviewed) and reconciled with scitex-dev's existing content-probe
doctrine (``_release._install_probe``). The domain vocabulary was
generalised — sac called it ``Freshness``; here it is ``Currency`` — but
the hard-won rule is carried over verbatim, stated once:

    A check that cannot reach its evidence reports UNKNOWN. It NEVER
    reports FRESH.

Both halves are load-bearing, and both were paid for in sac's outage:

* Treating "no evidence" as healthy is how a fix sits un-shipped for a
  day while agents re-diagnose it. Three consecutive tags never reached
  PyPI, and nothing anywhere said a word.
* Treating "no evidence" as *broken* is worse, because a false RED gets a
  remedy, and the remedy destroys a healthy thing (``pip install -U`` on
  an editable checkout clobbers the working tree with a wheel). So only
  :attr:`Currency.STALE` — positive evidence of staleness — is ever
  actionable. UNKNOWN is silent by construction.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

__all__ = ["Currency", "Finding", "Report"]


class Currency(enum.Enum):
    """The verdict for one version-currency check.

    * ``FRESH``   — positive evidence the thing is current.
    * ``STALE``   — positive evidence the thing is behind. Actionable.
    * ``UNKNOWN`` — the evidence could not be obtained (offline, no such
      file, unparseable version, no git checkout, ...). NOT a synonym for
      FRESH. Never actionable, never raised as an alarm.
    """

    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Finding:
    """The outcome of a single named check.

    Attributes:
        check: Stable machine id (``host-behind-pypi``, ``editable-drift``,
            ``ghost-tag``, ``running-vs-installed``, ``release-run``,
            ``symbol-probe``, ``install-integrity``).
        state: The :class:`Currency` verdict.
        summary: One human line. Shown to the operator when STALE.
            **It MUST name the binary that answered** — which package
            origin and which interpreter produced the verdict — so a
            reader can tell WHOSE "0.21.21 is behind 0.21.24" this is.
            :func:`scitex_dev.versioning._checks.build_report` stamps that
            tag onto every finding automatically.
        remedy: The exact command that fixes it. Empty when the fix is not
            a command a human can just run. An alarm that does not say
            what to *do* gets ignored. For an editable checkout the remedy
            is NEVER ``pip install -U`` — that would clobber the working
            tree; it is a ``git pull``.
        detail: Longer context; shown in ``--json`` and verbose output.
        data: Machine-readable evidence, including ``origin`` and
            ``executable`` once stamped.
    """

    check: str
    state: Currency
    summary: str
    remedy: str = ""
    detail: str = ""
    data: dict = field(default_factory=dict)

    @property
    def is_stale(self) -> bool:
        """True only on positive evidence of staleness.

        UNKNOWN is deliberately excluded — see the module docstring.
        """
        return self.state is Currency.STALE

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "state": self.state.value,
            "summary": self.summary,
            "remedy": self.remedy,
            "detail": self.detail,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Finding":
        """Rebuild from :meth:`to_dict` (the cache round-trip).

        An unrecognised state string decays to UNKNOWN rather than
        raising: a cache written by a future version must never break the
        CLI that reads it.
        """
        try:
            state = Currency(raw.get("state"))
        except ValueError:
            state = Currency.UNKNOWN
        return cls(
            check=str(raw.get("check", "")),
            state=state,
            summary=str(raw.get("summary", "")),
            remedy=str(raw.get("remedy", "")),
            detail=str(raw.get("detail", "")),
            data=dict(raw.get("data") or {}),
        )


@dataclass(frozen=True)
class Report:
    """All findings from one currency check, plus the aggregate verdict."""

    findings: tuple[Finding, ...] = ()
    generated_at: float = 0.0

    @property
    def state(self) -> Currency:
        """Aggregate verdict. Precedence is STALE > UNKNOWN > FRESH.

        * any STALE -> STALE. Positive evidence of a problem outranks
          everything; one un-shipped fix still matters when four other
          checks are clean.
        * else any UNKNOWN -> UNKNOWN. Partial blindness is never
          summarised as "fresh".
        * else FRESH.

        No findings at all is UNKNOWN, not FRESH — an empty report means
        nothing was checked, which is exactly the state this module exists
        to stop being read as good news.
        """
        if not self.findings:
            return Currency.UNKNOWN
        if any(f.state is Currency.STALE for f in self.findings):
            return Currency.STALE
        if any(f.state is Currency.UNKNOWN for f in self.findings):
            return Currency.UNKNOWN
        return Currency.FRESH

    @property
    def stale(self) -> tuple[Finding, ...]:
        """Just the actionable findings — all an alarm may speak about."""
        return tuple(f for f in self.findings if f.is_stale)

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "generated_at": self.generated_at,
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Report":
        return cls(
            findings=tuple(
                Finding.from_dict(f) for f in (raw.get("findings") or [])
            ),
            generated_at=float(raw.get("generated_at") or 0.0),
        )


# EOF
