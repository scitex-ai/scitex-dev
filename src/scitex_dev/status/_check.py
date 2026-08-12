#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""":class:`Check` — one named question, its verdict, and the words that go with it.

    Check.ok("store_canonical", "PostgreSQL store at ... (3469 cards, writable)")
    Check.not_ok("notifyd_alive", "no notifyd pidfile", hint="start it: `... notifyd`")
    Check.unknown("may_relocate", "compute-04 refused the probe 403 ...",
                  hint="upgrade the remote daemon, then re-run `sac relocate --check`",
                  cause=StatusCode(kind="http", code=403, message="..."))

Five fields, frozen, validated where it is BUILT — the same contract
:class:`~._status_code.StatusCode` keeps, for the same reason: a malformed
check discovered in the aggregate is a check whose producer can no longer be
identified.

THE REASON IS STRUCTURAL, NOT ENCOURAGED
----------------------------------------
:meth:`Check.unknown` takes its reason as a REQUIRED positional argument, so
the only path that produces an unknown cannot be walked without one; and
``__post_init__`` refuses a blank one, so the direct constructor cannot get
around it either. Both halves are needed. A rule that lives only in a
docstring is a rule that holds until the first hurry.

An unknown that says only "unknown" has not improved on the boolean it
replaced. It has given the reader a third word for guessing.

BORROW THE NATIVE CODE FOR ``cause``
------------------------------------
Where the failure to find out has a native code, carry it verbatim rather than
paraphrasing it: ``http 504`` ("I stopped waiting"), ``http 403``,
``errno ETIMEDOUT`` / ``EACCES`` / ``EHOSTUNREACH``, ``process 255`` (ssh
transport), ``grpc UNKNOWN``, ``dns SERVFAIL``. ADR-0007's argument applies
unchanged: a design that discards the native code to gain a shared word has
paid too much for the word.

``cause`` is OPTIONAL and is OMITTED from the wire form when absent, so a
report built without one serialises to exactly the four fields
``{name, ok, detail, hint}`` that every existing reader parses.

M1 IS NOT ENFORCED HERE, AND THAT WAS MEASURED
----------------------------------------------
An earlier draft applied ``message``'s no-inferred-cause marker list (M1) to
``detail`` and ``hint`` as a rule C5. It was tried against the first real
consumer and REFUSED a correct check: ``scitex-cards``' ``backend_mode`` says
cards are on postgres, the inbox is on yaml, and writes "therefore land in
different engines" — a deduction from two facts the check itself states, in
prose that records a dated measurement. The marker list is a heuristic tuned
for short status messages; a check's ``detail`` is long and explanatory by
design, so the false-positive rate is materially higher, and the very first
one tripped it.

The rule survives as guidance in ``verdicts.yaml``, unenforced, because the
STRUCTURAL protection against a check asserting what it did not observe is the
verdict itself: a checker that could not establish something reports
``unknown`` and says so. A word list is a poor second, and one that refuses the
first honest adopter gets the whole type bypassed — this package's own law is
that thin gets adopted and thick gets bypassed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._errors import CheckError
from ._status_code import StatusCode
from ._verdict import Verdict

__all__ = ["Check"]

#: The wire keys of one check record. ``cause`` is absent from this set on
#: purpose: it is emitted only when present, so the common record stays the
#: four fields that ``scitex-cards``' doctor, its CLI and its MCP tool already
#: read. Adding a fifth mandatory key would have made every existing reader
#: wrong about a shape that was not the problem.
_WIRE_KEYS = ("name", "ok", "detail", "hint")


def _require_text(field: str, value: Any, why: str) -> str:
    """Return a non-blank string, or raise :class:`CheckError` explaining what is missing."""
    if not isinstance(value, str) or not value.strip():
        raise CheckError(
            f"`{field}` must be a non-empty string; got {value!r}. {why}"
        )
    return value


@dataclass(frozen=True, kw_only=True, slots=True)
class Check:
    """One check's answer. Build it through :meth:`ok`, :meth:`not_ok` or :meth:`unknown`.

    Keyword-only, so the fields cannot be swapped by position — a check whose
    detail and hint have traded places is one nobody notices until it is read
    in an incident.
    """

    name: str
    verdict: Verdict
    detail: str
    hint: "str | None" = None
    cause: "StatusCode | None" = None

    def __post_init__(self) -> None:
        # C1 — an anonymous check cannot be followed across runs, cannot be
        # named in a summary, and cannot be the subject of a bug report.
        _require_text(
            "name",
            self.name,
            "A check is a named question; without the name the answer cannot "
            "be attributed to anything.",
        )

        # C2 — no default verdict. Every default is a guess wearing a type.
        if not isinstance(self.verdict, Verdict):
            raise CheckError(
                f"`verdict` must be a Verdict member; got {self.verdict!r} "
                f"({type(self.verdict).__name__}). Use Verdict.OK / "
                f"Verdict.NOT_OK / Verdict.UNKNOWN, or parse an incoming "
                f"value with Verdict.from_wire(...) or Verdict.from_ok(...). "
                f"A bare string is refused so that a comparison against the "
                f"wrong string fails loudly instead of quietly."
            )

        # C3 — a check that says nothing about what it observed cannot be
        # checked by its reader, whichever way it answered.
        _require_text(
            "detail",
            self.detail,
            "State what was OBSERVED. For an `unknown` this is the REASON it "
            "could not be determined, and it is the whole difference between "
            "a three-valued verdict and a boolean with an extra name.",
        )

        # C4 — not-ok says what to DO; unknown says how to FIND OUT.
        if self.verdict is Verdict.NOT_OK:
            _require_text(
                "hint",
                self.hint,
                "A `not-ok` check MUST say what to do about it. An error that "
                "only states what broke is half-written.",
            )
        if self.verdict is Verdict.UNKNOWN:
            _require_text(
                "hint",
                self.hint,
                "An `unknown` check MUST say how to FIND OUT — the probe to "
                "run, the thing to upgrade, the permission to grant. Without "
                "it the reader can only wait and then guess, which is the "
                "2026-08-11 incident exactly.",
            )

        if self.cause is not None and not isinstance(self.cause, StatusCode):
            raise CheckError(
                f"`cause` must be a StatusCode or None; got {self.cause!r}. "
                f"It exists to carry the NATIVE code behind this verdict "
                f"verbatim — http 403, errno ETIMEDOUT, process 255 — because "
                f"the native code is the specific fact and the verdict is only "
                f"the decision taken from it."
            )

    # -- the three constructors --------------------------------------------
    #
    # These are the intended way in. `unknown` takes its reason POSITIONALLY
    # and REQUIRED, which is the structural half of the "an unknown must say
    # why" rule: the path cannot be walked without one.

    @classmethod
    def ok(
        cls,
        name: str,
        detail: str,
        *,
        hint: "str | None" = None,
        cause: "StatusCode | None" = None,
    ) -> "Check":
        """Asked, answered, good. ``detail`` states the evidence, not the absence of doubt."""
        return cls(
            name=name, verdict=Verdict.OK, detail=detail, hint=hint, cause=cause
        )

    @classmethod
    def not_ok(
        cls,
        name: str,
        detail: str,
        hint: str,
        *,
        cause: "StatusCode | None" = None,
    ) -> "Check":
        """Asked, answered, bad. ``hint`` is required: say what to do about it."""
        return cls(
            name=name, verdict=Verdict.NOT_OK, detail=detail, hint=hint, cause=cause
        )

    @classmethod
    def unknown(
        cls,
        name: str,
        reason: str,
        hint: str,
        *,
        cause: "StatusCode | None" = None,
    ) -> "Check":
        """Could not find out. ``reason`` says WHY; ``hint`` says HOW TO FIND OUT.

        Both are required positionally. That is deliberate: an unknown is the
        one verdict whose whole value is the sentence beside it, so the type
        does not offer a way to produce a bare one.
        """
        return cls(
            name=name,
            verdict=Verdict.UNKNOWN,
            detail=reason,
            hint=hint,
            cause=cause,
        )

    # -- wire form ----------------------------------------------------------

    def to_dict(self) -> "dict[str, Any]":
        """The wire form: the four familiar fields, plus ``cause`` only when set.

        The verdict rides in ``ok`` as ``true`` / ``false`` / ``null`` rather
        than in a field of its own. One field, three values, nothing that can
        disagree with anything else — and every reader of the four-field
        record keeps working.
        """
        payload: "dict[str, Any]" = {
            "name": self.name,
            "ok": self.verdict.ok,
            "detail": self.detail,
            "hint": self.hint,
        }
        if self.cause is not None:
            payload["cause"] = self.cause.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: "dict[str, Any]") -> "Check":
        """Parse a wire form, validating it. Refuses unknown keys rather than ignoring them."""
        extra = set(payload) - set(_WIRE_KEYS) - {"cause"}
        if extra:
            raise CheckError(
                f"unexpected key(s) {sorted(extra)} in a check record. The "
                f"record is {list(_WIRE_KEYS)}, plus an optional `cause`. In "
                f"particular a separate `status`/`verdict` key is refused: the "
                f"verdict travels in `ok` as true/false/null, and a second "
                f"field saying the same thing is a second field that can "
                f"disagree."
            )
        cause = payload.get("cause")
        return cls(
            name=payload["name"],
            verdict=Verdict.from_ok(payload.get("ok")),
            detail=payload.get("detail", ""),
            hint=payload.get("hint"),
            cause=None if cause is None else StatusCode.from_dict(cause),
        )


# EOF
