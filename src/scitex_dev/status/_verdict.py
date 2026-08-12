#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""":class:`Verdict` — the three answers a check may give, DERIVED from ``spec/verdicts.yaml``.

THREE ANSWERS, NOT TWO
----------------------
``ok`` — I asked, and the answer is good.
``not-ok`` — I asked, and the answer is bad.
``unknown`` — I could not find out.

A boolean has no room for the third, so it forces every "I could not find out"
to be filed as one of its neighbours, and both filings are false. Measured in
this fleet on 2026-08-11: nine relocation probes were refused ``http 403`` by
hosts running a daemon too old to have the endpoint. Read as ``not-ok`` that
grounds nine healthy agents; read as ``ok`` it moves an agent onto a host
nobody inspected. The same day, a card-store doctor that could not open its
store reported ``ok: false`` on two checks whose questions it never asked.

UNKNOWN IS NOT A DEFAULT AND NOT A FALLBACK
-------------------------------------------
It is a MEASURED outcome: the checker tried and could not tell. A checker that
has not run yet has no verdict at all — which is the absence of a check, not
this value. :class:`~._check.Check` enforces the difference by refusing an
``unknown`` that carries no reason.

WHY THIS IS NOT THE FORBIDDEN STORED ``ok``
-------------------------------------------
``status-codes.md`` §8 forbids storing ``ok`` beside a
:class:`~._status_code.StatusCode`, because there it is DERIVABLE from the code
and two fields that can disagree eventually will. A verdict is not derivable,
because THE SAME CODE MEANS DIFFERENT VERDICTS DEPENDING ON THE QUESTION
ASKED. ``http 403`` answering *"am I allowed to do this?"* is a definite
``not-ok``. The same 403 answering *"may this agent relocate?"*, returned by a
daemon that has never heard of the endpoint, is ``unknown``. Deriving one from
the other is the collapse, not the cure.

THE WIRE FORM IS THE TRI-STATE ``ok`` FIELD
-------------------------------------------
On the wire a verdict travels as the doctor report's ``ok`` field, three-valued
as JSON ``true`` / ``false`` / ``null`` — see :meth:`Verdict.ok` and
:meth:`Verdict.from_ok`. It rides in the EXISTING field rather than a new one
so that every reader of the four-field check record keeps working, and so that
there are never two fields that can disagree about the same answer. A reader
that only understands booleans sees ``null``, which is falsy in both Python and
JavaScript — unknown then reads as "not fine", which is the safe direction.
"""

from __future__ import annotations

import enum
from functools import lru_cache

from ._errors import UnknownVerdictError
from ._spec import load_verdicts

__all__ = ["Verdict", "verdicts"]


class Verdict(enum.Enum):
    """The verdict of ONE check. Closed set of three; none is a default.

    Plain :class:`enum.Enum` rather than ``(str, Enum)`` on purpose. A string
    mixin would make ``Verdict.OK == "ok"`` true, so a caller comparing against
    a bare string would silently succeed — and silent success on an unchecked
    comparison is how the distinction gets lost again. Ask for the wire value
    explicitly: :attr:`Verdict.value` or :meth:`Verdict.ok`.
    """

    #: Asked, answered, and the answer is the good one. POSITIVE evidence —
    #: never the mere absence of bad evidence. "Nothing went wrong" and "I did
    #: not look" are different sentences and only the first one is this value.
    OK = "ok"

    #: Asked, answered, and the answer is the bad one. Positive evidence of a
    #: problem, and therefore actionable — which is why :class:`~._check.Check`
    #: requires a hint saying what to do about it.
    NOT_OK = "not-ok"

    #: Could not find out. Unreachable host, elapsed deadline, refused
    #: permission, a remote too old to have the endpoint, a store that would
    #: not open. NOT a synonym for either neighbour.
    UNKNOWN = "unknown"

    @classmethod
    def from_wire(cls, value: object) -> "Verdict":
        """Parse the spec's string form, or raise.

        Refuses an unrecognised value rather than decaying it to ``UNKNOWN``.
        Decaying looks charitable and is not: a reader that silently accepts a
        verdict it does not implement reports a value nobody sent, and
        ``status-codes.md`` §9 already rules that partially understanding a
        protocol message is how a field's absence gets read as a value.
        """
        for member in cls:
            if member.value == value:
                return member
        raise UnknownVerdictError(
            f"unknown verdict {value!r}. The set is closed and has three "
            f"members: {[m.value for m in cls]}. If the checker could not "
            f"find out, that is {cls.UNKNOWN.value!r} WITH a reason — not a "
            f"new word, and not a blank."
        )

    @property
    def ok(self) -> "bool | None":
        """The wire form: ``True`` / ``False`` / ``None``.

        ``None`` is UNKNOWN, and it rides in the ``ok`` field rather than in a
        fifth key so that the four-field check record every existing reader
        parses keeps working unchanged.
        """
        if self is Verdict.OK:
            return True
        if self is Verdict.NOT_OK:
            return False
        return None

    @classmethod
    def from_ok(cls, value: object) -> "Verdict":
        """Parse the tri-state ``ok`` field, or raise.

        Strict about the three JSON values it accepts. ``1`` and ``0`` are
        refused even though Python would happily treat them as booleans,
        because a truthiness coercion is exactly how a third state gets eaten:
        ``bool(x)`` maps every non-empty value onto ``True``, including the one
        that meant "I could not tell".
        """
        if value is None:
            return cls.UNKNOWN
        if value is True:
            return cls.OK
        if value is False:
            return cls.NOT_OK
        raise UnknownVerdictError(
            f"the `ok` field is THREE-VALUED and carries exactly true, false "
            f"or null; got {value!r} ({type(value).__name__}). Truthy "
            f"stand-ins are refused on purpose: `bool({value!r})` would map it "
            f"onto one of the two answers and destroy the third."
        )


@lru_cache(maxsize=None)
def verdicts() -> "tuple[str, ...]":
    """Every declared verdict, in spec order.

    Read from ``spec/verdicts.yaml`` so the spec is the source of truth and
    this module is a reader of it, exactly as :func:`~._kinds.kinds` reads
    ``kinds.yaml``.
    """
    return tuple(entry["verdict"] for entry in load_verdicts()["verdicts"])


# EOF
